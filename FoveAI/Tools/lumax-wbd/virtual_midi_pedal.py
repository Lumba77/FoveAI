import collections
import threading
import time

import cv2
import mediapipe as mp
import mido
from ai_drum_creator import get_creative_mapping
from fastdtw import fastdtw
from scipy.spatial.distance import euclidean

# Configuration
MIDI_PORT_NAME = "loopMIDI Port"  # User should create this in loopMIDI
KICK_NOTE = 36  # Standard GM Kick Drum
HIHAT_NOTE = 44  # Standard GM Pedal Hi-Hat


# Heuristic Constants Configurable by Mode
class DrumMode:
    EXPERT = {
        "velocity_threshold": 0.03,  # Adjusted for webcam space (normalized coordinates)
        "cooldown_frames": 5,
    }
    CASUAL = {"velocity_threshold": 0.015, "cooldown_frames": 15}
    FREE = {
        "velocity_threshold": 0.005,  # Ultra sensitive
        "cooldown_frames": 8,
    }


CURRENT_MODE = DrumMode.FREE


class KneeTracker:
    def __init__(self, name, midi_out, note, mode_config):
        self.name = name
        self.midi_out = midi_out
        self.note = note
        self.config = mode_config

        self.y_history = collections.deque(maxlen=60)
        self.time_history = collections.deque(maxlen=60)

        # Co-Creation Variables
        self.signatures = []  # List of dicts: {"pattern": [y1, y2...], "note": note}
        self.is_recording_gesture = False
        self.current_gesture = []
        self.idle_frames = 0
        self.gesture_count = 0

        self.cooldown = 0
        self.is_falling = False
        self.max_velocity = 0.0

    def add_signature(self, pattern, note):
        self.signatures.append({"pattern": pattern, "note": note})

    def evaluate_gesture(self, gesture_data):
        if len(gesture_data) < 5:
            return

        print(f"[{self.name}] Analyzing gesture (length: {len(gesture_data)})...")
        best_dist = float("inf")
        best_sig = None

        for sig in self.signatures:
            distance, path = fastdtw(gesture_data, sig["pattern"], dist=euclidean)
            if distance < best_dist:
                best_dist = distance
                best_sig = sig

        if best_sig and best_dist < 0.15:
            self.note = best_sig["note"]
            self.trigger_midi()
            print(f"[{self.name}] Matched signature! Distance: {best_dist:.3f}")
        else:
            print(
                f"[{self.name}] New unique gesture detected (Best dist: {best_dist:.3f})"
            )
            self.gesture_count += 1

            speed = "Fast" if len(gesture_data) < 15 else "Slow"
            depth = max(gesture_data) - min(gesture_data)
            depth_str = "Large" if depth > 0.1 else "Small"

            profile = f"- Tracker: {self.name}\n- Speed: {speed}\n- Depth: {depth_str}"

            def get_suggestion():
                print(f"[{self.name}] Asking AI for creative mapping...")
                suggestion = get_creative_mapping(profile, self.gesture_count)
                if suggestion:
                    print("\n=========================================")
                    print(f"🤖 AI CO-CREATOR SUGGESTION for {self.name}")
                    print(
                        f"Suggestion: {suggestion['name']} (Note {suggestion['note']})"
                    )
                    print(f"Rationale: {suggestion['rationale']}")
                    print("=========================================\n")
                    self.add_signature(gesture_data, suggestion["note"])
                    self.note = suggestion["note"]
                    self.trigger_midi()

            threading.Thread(target=get_suggestion).start()

    def update(self, y_normalized, current_time):
        # In OpenCV/MediaPipe, Y=0 is TOP of screen, Y=1 is BOTTOM.
        # To match our old logic (where moving DOWN is a negative velocity), we invert Y.
        y_inverted = 1.0 - y_normalized
        self.y_history.append(y_inverted)
        self.time_history.append(current_time)

        if self.cooldown > 0:
            self.cooldown -= 1
            return False

        if len(self.y_history) >= 3:
            y_curr = self.y_history[-1]
            y_prev = self.y_history[-2]

            t_curr = self.time_history[-1]
            t_prev = self.time_history[-2]

            dt = t_curr - t_prev
            if dt == 0:
                dt = 0.001

            velocity = (y_curr - y_prev) / dt

            # Gesture recording logic
            if abs(velocity) > 0.05:  # Movement detected
                self.is_recording_gesture = True
                self.current_gesture.append(y_curr)
                self.idle_frames = 0
            else:
                self.idle_frames += 1

            if self.is_recording_gesture and self.idle_frames > 15:  # Stopped moving
                self.evaluate_gesture(list(self.current_gesture))
                self.current_gesture = []
                self.is_recording_gesture = False
                self.idle_frames = 0

            # Keep original heuristic for standard triggers
            if velocity < 0:  # Moving down (y_inverted decreases)
                self.is_falling = True
                self.max_velocity = max(self.max_velocity, abs(velocity))

            elif velocity >= 0 and self.is_falling:
                if self.max_velocity > self.config["velocity_threshold"]:
                    # BOUNCE DETECTED!
                    self.trigger_midi()
                    self.cooldown = self.config["cooldown_frames"]
                    self.is_falling = False
                    self.max_velocity = 0.0
                    return True
                else:
                    self.is_falling = False
                    self.max_velocity = 0.0

        return False

    def trigger_midi(self):
        if self.midi_out:
            msg_on = mido.Message("note_on", note=self.note, velocity=100)
            self.midi_out.send(msg_on)
            print(f"[{self.name}] BOUNCE DETECTED! -> Sent MIDI {self.note}")

            def off():
                time.sleep(0.1)
                msg_off = mido.Message("note_off", note=self.note, velocity=0)
                self.midi_out.send(msg_off)

            threading.Thread(target=off).start()
        else:
            print(f"[{self.name}] BOUNCE DETECTED! (No MIDI output configured)")


def main():
    # Setup MIDI Output
    midi_out = None
    available_ports = mido.get_output_names()
    print("Available MIDI Ports:", available_ports)

    for port in available_ports:
        if MIDI_PORT_NAME.lower() in port.lower():
            try:
                midi_out = mido.open_output(port)
                print(f"Successfully opened MIDI port: {port}")
                break
            except Exception as e:
                print(f"Error opening port {port}: {e}")

    if not midi_out and available_ports:
        print(
            "Warning: Could not find loopMIDI port. Using fallback port for testing..."
        )
        try:
            midi_out = mido.open_output(available_ports[0])
            print(f"Opened fallback MIDI port: {available_ports[0]}")
        except Exception:
            print("Failed to open any MIDI port.")

    # Initialize Trackers with the selected Mode
    left_knee_tracker = KneeTracker(
        "Left Knee (Hi-Hat)", midi_out, HIHAT_NOTE, CURRENT_MODE
    )
    right_knee_tracker = KneeTracker(
        "Right Knee (Kick)", midi_out, KICK_NOTE, CURRENT_MODE
    )

    # Initialize MediaPipe Pose
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1,  # 0, 1, or 2 (1 is default/good balance)
    )
    mp_drawing = mp.solutions.drawing_utils

    print("Starting Webcam...")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    print("Point your webcam so it can see your legs/knees.")
    print("Press 'q' in the video window to quit.")

    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("Ignoring empty camera frame.")
            continue

        # To improve performance, optionally mark the image as not writeable to pass by reference.
        image.flags.writeable = False
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = pose.process(image)

        # Draw the pose annotation on the image.
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS
            )

            landmarks = results.pose_landmarks.landmark

            # MediaPipe Landmark 25 is Left Knee, 26 is Right Knee
            # (Note: MediaPipe left/right is from the person's perspective)
            left_knee_y = landmarks[25].y
            right_knee_y = landmarks[26].y

            current_time = time.time()

            # Only update if the landmarks are actually visible (visibility > 0.5)
            if landmarks[25].visibility > 0.5:
                left_knee_tracker.update(left_knee_y, current_time)

            if landmarks[26].visibility > 0.5:
                right_knee_tracker.update(right_knee_y, current_time)

        # Flip the image horizontally for a selfie-view display.
        cv2.imshow("MediaPipe Pose - AI Drum Pedal", cv2.flip(image, 1))
        if cv2.waitKey(5) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    if midi_out:
        midi_out.close()


if __name__ == "__main__":
    main()
