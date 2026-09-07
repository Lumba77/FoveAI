import time
from pythonosc import udp_client

# Connect to the Wonder Pedal Bridge running locally
client = udp_client.SimpleUDPClient("127.0.0.1", 9005)

print("Simulating Wonder Pedal hits...")

print("-> Triggering Kick Drum")
client.send_message("/wonderpedal/kick", [])
time.sleep(1)

print("-> Triggering Hi-Hat")
client.send_message("/wonderpedal/hihat", [])
time.sleep(1)

print("-> Quick Double Kick")
client.send_message("/wonderpedal/kick", [])
time.sleep(0.15)
client.send_message("/wonderpedal/kick", [])

print("\nMock tests completed! Check the Bridge console for MIDI output.")
