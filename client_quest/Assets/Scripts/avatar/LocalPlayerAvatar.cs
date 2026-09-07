using Oculus.Avatar2;
using UnityEngine;

namespace FoveAI
{
    public class LocalPlayerAvatar : OvrAvatarEntity
    {
        public void SetUserId(ulong userId)
        {
            _userId = userId;
        }

        public void LoadLocalUser()
        {
            // Call the protected LoadUser method provided by the Meta Avatar SDK
            LoadUser();
        }
    }
}
