using UnityEngine;

namespace FoveAI.Avatar
{
    /// <summary>
    /// Drives Didimo / CC4 avatar facial blendshapes and visemes from IPC events.
    /// </summary>
    public class AvatarBlendshapeDriver : MonoBehaviour
    {
        [SerializeField] private SkinnedMeshRenderer faceMesh;

        public void SetVisemeWeight(string visemeName, float weight)
        {
            if (faceMesh == null) return;
            int index = faceMesh.sharedMesh.GetBlendShapeIndex(visemeName);
            if (index != -1)
            {
                faceMesh.SetBlendShapeWeight(index, Mathf.Clamp01(weight) * 100f);
            }
        }
    }
}
