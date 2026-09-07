using UnityEngine;
using UnityEngine.XR;
using System.Collections.Generic;

namespace FoveAI.Environment
{
    /// <summary>
    /// Simple and flawless HMD tracker that replaces TrackedPoseDriver.
    /// Reads CenterEye position and rotation directly from the Unity XR subsystem.
    /// Works perfectly on Quest 3 / OpenXR without needing complex InputSystem binding assets.
    /// </summary>
    public class HMDTracker : MonoBehaviour
    {
        private List<XRNodeState> _nodeStates = new List<XRNodeState>();

        void Update()
        {
            InputTracking.GetNodeStates(_nodeStates);
            foreach (var state in _nodeStates)
            {
                if (state.nodeType == XRNode.CenterEye || state.nodeType == XRNode.Head)
                {
                    if (state.TryGetPosition(out Vector3 pos))
                    {
                        transform.localPosition = pos;
                    }
                    if (state.TryGetRotation(out Quaternion rot))
                    {
                        transform.localRotation = rot;
                    }
                    break;
                }
            }
        }
    }
}
