# Wonder Pedal - Unity Setup Guide

This guide explains how to open the cloned `vrdm` project in Unity, install the Meta Movement SDK, and rig the Wonder Pedal tracker script to a full-body VR drumset.

## 1. Open the Project
1. Open **Unity Hub** and click **Add**.
2. Select the folder: `C:\Users\danie\program\LUMAX\Tools\WonderPedal\WonderPedalUnity\vrdm`.
3. *(It will ask you to install Unity 2021.3.4f1 if you don't have it. Make sure you check "Android Build Support" during installation).*

## 2. Import the Meta SDK
1. Once Unity opens, go to **Window > Package Manager**.
2. Click the tiny `+` icon in the top left and select **Add package from git URL**.
3. Type `com.meta.xr.sdk.movement` and hit Enter.

## 3. Rig the Pedal
1. Open the main drumming Scene.
2. In your Project folder, search for **OVRCameraRig** and drag it into the scene (this is your VR headset/body).
3. On that rig, check the box to enable **Body Tracking**.
4. In your Hierarchy, right-click and create an **Empty GameObject**. Name it `Wonder Pedal`.
5. Drag the `WonderPedalTracker.cs` script (located in the `Assets/` folder) onto this new object.
6. Now, just drag your Foot bone (found inside the OVRCameraRig's body tracking skeleton) into the `Tracked Foot` slot on the script!
7. Make sure the `pcBridgeIp` in the script is set to your computer's local IP address.

## 4. Build the APK
1. Go to **File > Build Settings**.
2. Switch the platform to **Android**.
3. Click **Build and Run** (with your Quest plugged in).

When you run this on your Quest, start the `paradiddle_bridge.py` on your PC, and enjoy your full-body tracking double kick pedal!
