import time

from pythonosc import udp_client

client = udp_client.SimpleUDPClient("127.0.0.1", 9000)

print("Sending mock Left Knee movements...")
# Move knee up (Y increases, wait, in 3D Y up means increasing)
client.send_message("/tracking/trackers/1/position", [0.0, 1.0, 0.0])
time.sleep(0.05)
client.send_message("/tracking/trackers/1/position", [0.0, 0.8, 0.0])  # Moving down
time.sleep(0.05)
client.send_message(
    "/tracking/trackers/1/position", [0.0, 0.5, 0.0]
)  # Moving down fast
time.sleep(0.05)
client.send_message(
    "/tracking/trackers/1/position", [0.0, 0.5, 0.0]
)  # Stopped (bounce!)
time.sleep(0.05)
client.send_message("/tracking/trackers/1/position", [0.0, 0.6, 0.0])  # Moving back up

print("Sending mock Right Knee movements...")
time.sleep(1)
client.send_message("/tracking/trackers/2/position", [0.0, 1.0, 0.0])
time.sleep(0.05)
client.send_message("/tracking/trackers/2/position", [0.0, 0.5, 0.0])  # Fast down
time.sleep(0.05)
client.send_message("/tracking/trackers/2/position", [0.0, 0.5, 0.0])  # Bounce

print("Mock OSC data sent!")
