/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * Licensed under the Oculus SDK License Agreement (the "License");
 * you may not use the Oculus SDK except in compliance with the License,
 * which is provided at the time of installation or download, or which
 * otherwise accompanies this software in either electronic or hard copy form.
 *
 * You may obtain a copy of the License at
 *
 * https://developer.oculus.com/licenses/oculussdk/
 *
 * Unless required by applicable law or agreed to in writing, the Oculus SDK
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#nullable enable

using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace Oculus.Avatar2
{
    public class CollapsibleSectionCustomInspector : Editor
    {
        private const int FONT_SIZE = 12;
        private const FontStyle FONT_STYLE_TYPE = FontStyle.Bold;

        private readonly Dictionary<string, bool> _foldoutStates = new();
        private GUIStyle? _foldoutStyle;

        private GUIStyle GetFoldoutStyle()
        {
            if (_foldoutStyle == null)
            {
                _foldoutStyle = new GUIStyle(EditorStyles.foldout)
                {
                    fontSize = FONT_SIZE,
                    fontStyle = FONT_STYLE_TYPE,
                };
            }
            return _foldoutStyle;
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            SerializedProperty property = serializedObject.GetIterator();
            bool insideHiddenSection = false;
            bool isSectionOpen = false;

            if (property.NextVisible(true))
            {
                do
                {
                    var attributeStart = GetAttribute<CollapsibleSectionStartAttribute>(property);
                    var attributeEnd = GetAttribute<CollapsibleSectionEndAttribute>(property);

                    if (attributeStart != null)
                    {
                        // Start of a collapsible section.
                        insideHiddenSection = true;
                        string currentSectionTitle = attributeStart.SectionTitle;

                        if (!_foldoutStates.TryGetValue(currentSectionTitle, out isSectionOpen))
                        {
                            isSectionOpen = !attributeStart.StartCollapsed;
                            _foldoutStates[currentSectionTitle] = isSectionOpen;
                        }

                        GUIStyle foldoutStyle = GetFoldoutStyle();
                        foldoutStyle.normal.textColor = attributeStart.TextColor; // Set the foldout text color from attribute
                        foldoutStyle.onNormal.textColor = attributeStart.TextColor;

                        // Draw the foldout with the custom style and color
                        isSectionOpen = EditorGUILayout.Foldout(isSectionOpen, attributeStart.SectionTitle, true, GetFoldoutStyle());
                        _foldoutStates[currentSectionTitle] = isSectionOpen;

                        if (isSectionOpen)
                        {
                            EditorGUILayout.PropertyField(property, true);
                        }
                    }
                    else if (attributeEnd != null) // End of a collapsible section
                    {
                        if (insideHiddenSection && isSectionOpen)
                        {
                            EditorGUILayout.PropertyField(property, true);
                        }
                        insideHiddenSection = false;
                    }
                    else if (insideHiddenSection && isSectionOpen) // Within an open section
                    {
                        EditorGUILayout.PropertyField(property, true);
                    }
                    else if (!insideHiddenSection) // Not inside a collapsible section
                    {
                        EditorGUILayout.PropertyField(property, true);
                    }
                } while (property.NextVisible(false));
            }

            serializedObject.ApplyModifiedProperties();
        }

        // Gets the attribute of the specified type from the serialized property
        private T? GetAttribute<T>(SerializedProperty property) where T : Attribute
        {
            FieldInfo? fieldInfo = GetFieldBySerializedProperty(property);
            if (fieldInfo == null) return null;
            return (T)Attribute.GetCustomAttribute(fieldInfo, typeof(T));
        }

        // Retrieves the FieldInfo for the given SerializedProperty by searching the property's declaring type
        private FieldInfo? GetFieldBySerializedProperty(SerializedProperty property)
        {
            if (property?.serializedObject == null ||
                property.serializedObject.targetObject == null)
            {
                return null;
            }
            Type type = property.serializedObject.targetObject.GetType();
            while (type != null)
            {
                FieldInfo fieldInfo = type.GetField(property.name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                if (fieldInfo != null)
                    return fieldInfo;
                type = type.BaseType;
            }
            return null;
        }
    }

    [CustomEditor(typeof(OvrAvatarEntity), true, isFallback = true)]
    public class OvrAvatarEntityCustomInspector : CollapsibleSectionCustomInspector
    {
    }
}
