using UnityEngine;
using Oculus.Platform;
using Oculus.Platform.Models;
using System;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Hooks into the Meta Entitlement API to fetch the real user's Oculus ID 
    /// over the Meta Quest Network, overriding the generic sample avatar.
    /// </summary>
    public class UserAvatarManager : MonoBehaviour
    {
        public Action<ulong> OnUserLoggedIn;

        private void Start()
        {
            // 1. Initialize the Oculus Platform
            Core.AsyncInitialize().OnComplete(OnInitializationCallback);
        }

        private void OnInitializationCallback(Message<PlatformInitialize> msg)
        {
            if (msg.IsError)
            {
                Debug.LogError($"[UserAvatarManager] Oculus Platform Init Error: {msg.GetError().Message}");
            }
            else
            {
                Debug.Log("[UserAvatarManager] Oculus Platform Initialized successfully.");
                // 2. Check Entitlement
                Entitlements.IsUserEntitledToApplication().OnComplete(OnEntitlementCallback);
            }
        }

        private void OnEntitlementCallback(Message msg)
        {
            if (msg.IsError)
            {
                Debug.LogError($"[UserAvatarManager] Entitlement Error: {msg.GetError().Message}");
            }
            else
            {
                // 3. Fetch Logged In User
                Users.GetLoggedInUser().OnComplete(OnGetLoggedInUserCallback);
            }
        }

        private void OnGetLoggedInUserCallback(Message<User> msg)
        {
            if (msg.IsError)
            {
                Debug.LogError($"[UserAvatarManager] GetLoggedInUser Error: {msg.GetError().Message}");
            }
            else
            {
                ulong userId = msg.Data.ID;
                Debug.Log($"[UserAvatarManager] Logged in as Oculus User ID: {userId}");
                OnUserLoggedIn?.Invoke(userId);

                // Note: If using OvrAvatarEntity from the SDK, we inject the ID here.
                // It dynamically loads the user's avatar from the network.
                var avatarEntity = GetComponentInChildren<LocalPlayerAvatar>();
                if (avatarEntity != null)
                {
                    avatarEntity.SetUserId(userId);
                    avatarEntity.LoadLocalUser();
                }
                else
                {
                    Debug.LogWarning("[UserAvatarManager] No LocalPlayerAvatar found in children to inject user ID.");
                }
            }
        }
    }
}
