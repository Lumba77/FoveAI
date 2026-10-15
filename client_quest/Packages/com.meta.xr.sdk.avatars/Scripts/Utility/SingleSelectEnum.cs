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


#nullable disable

using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Oculus.Avatar2
{
    /// <summary>
    /// SingleSelectEnumAttribute implements a PropertyAttribute for an enum that
    /// can only select one option at a time, even if the EnumType uses FlagsAttribute.
    /// Enum values can also be hidden so they don't appear in the popup selection field.
    /// </summary>
    public class SingleSelectEnumAttribute : PropertyAttribute
    {
        private const string logScope = "SingleSelectEnumAttribute";

        private Type enumType = null;

        public Type EnumType
        {
            get => enumType;
            set
            {
                // Prevent the use of null or non-enum types.
                if (value == null)
                {
                    Oculus.Avatar2.OvrAvatarLog.LogError("EnumType cannot be null", logScope);
                    return;
                }
                else if (!value.IsEnum)
                {
                    Oculus.Avatar2.OvrAvatarLog.LogError("Type provided for EnumType is not an enum", logScope);
                    return;
                }

                enumType = value;
            }
        }

        /// <summary>
        /// If there are any values you don't want displayed in the property's
        /// popup selection field, add them to this array and they'll be hidden.
        /// </summary>
        public int[] HiddenValues = { };

        public bool IsValid() { return EnumType != null; }
    }

#if UNITY_EDITOR
    /// <summary>
    /// SingleSelectEnumAttributeEditor implements the PropertyDrawer for SingleSelectEnumAttribute.
    /// </summary>
    [CustomPropertyDrawer(typeof(SingleSelectEnumAttribute))]
    public class SingleSelectEnumAttributeEditor : PropertyDrawer
    {
        private const string logScope = "SingleSelectEnumAttributeEditor";

        public override void OnGUI(Rect position, SerializedProperty property, GUIContent label)
        {
            SingleSelectEnumAttribute customizableEnumAttribute = (SingleSelectEnumAttribute)attribute;

            // Verify that the attribute is valid.
            if (!customizableEnumAttribute.IsValid())
            {
                Oculus.Avatar2.OvrAvatarLog.LogError("SingleSelectEnumAttribute is not valid", logScope);
                return;
            }
            List<GUIContent> displayedOptions = new List<GUIContent>();
            List<int> displayedValues = new List<int>();

            // Get the display names and integer values of each option in the enum.
            foreach (object enumValue in Enum.GetValues(customizableEnumAttribute.EnumType))
            {
                // If the value is present in HiddenValues, we'll skip it.
                if (customizableEnumAttribute.HiddenValues.Contains((int)enumValue))
                {
                    continue;
                }
                displayedOptions.Add(new GUIContent(enumValue.ToString()));
                displayedValues.Add((int)enumValue);
            }

            property.intValue = EditorGUI.IntPopup(position, label, property.intValue, displayedOptions.ToArray(), displayedValues.ToArray());
        }
    }
#endif // UNITY_EDITOR
}
