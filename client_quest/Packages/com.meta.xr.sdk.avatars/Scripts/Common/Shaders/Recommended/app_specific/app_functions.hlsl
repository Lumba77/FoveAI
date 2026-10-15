// App specific functions that can be called from the exported Library shader
// If your app needs its own declarations, rename this file with your app's name and place them here.
// This file should persist across successive integrations.

// This function allows for app specific operations at the end of the vertex shader
void AppSpecificVertexPostManipulation(AvatarVertexInput i, inout VertexToFragment o) {
  // Call app specific functions from here.
}

// This function allows for app specific operations at the beginning of the fragment shader
void AppSpecificPreManipulation(inout avatar_FragmentInput i) {
  // Call app specific functions from here.
}

// This function allows for app specific operations in the middle of the fragment shader, before the components are combined
void AppSpecificFragmentComponentManipulation(avatar_FragmentInput i, inout float3 punctualSpecular, inout float3 punctualDiffuse, inout float3 ambientSpecular, inout float3 ambientDiffuse) {
  // Call app specific functions from here.
}

// This function allows for app specific operations at the beginning of the fragment shader
void AppSpecificPostManipulation(avatar_FragmentInput i, inout avatar_FragmentOutput o) {
  // Call app specific functions from here.
}
