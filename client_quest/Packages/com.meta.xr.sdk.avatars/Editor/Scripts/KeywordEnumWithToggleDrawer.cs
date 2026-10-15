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

using UnityEngine;
using UnityEditor;

// Shamelessly copied from Unity source and modified from MaterialKeywordEnumDrawer
// https://github.com/Unity-Technologies/UnityCsReference/blob/2021.3/Editor/Mono/Inspector/MaterialPropertyDrawer.cs

// Specify keywords to potentially set as well as a "enabled" keyword that is set when a different keyword is NOT enabled
public class KeywordEnumWithToggleDrawer : MaterialPropertyDrawer
{
    private readonly GUIContent[] _keywordsToChooseFrom;
    private readonly string _disabledKeyword;
    private readonly string _enabledKeyword;

    // Enable a keyword "enableKeyword" when they keyword "NoneKeyword" is not enabled.
    public KeywordEnumWithToggleDrawer(string enabledKeyword, string disabledKeyword, params string[] keywords)
    {
        // The potential keywords to choose from in the inspector UI are  disabledKeyword + other "enum" keywords
        int numToChooseFrom = keywords.Length + 1;
        _keywordsToChooseFrom = new GUIContent[numToChooseFrom];
        _keywordsToChooseFrom[0] = new GUIContent(disabledKeyword);

        for (int i = 1; i < numToChooseFrom; ++i)
        {
            _keywordsToChooseFrom[i] = new GUIContent(keywords[i - 1]);
        }

        _enabledKeyword = enabledKeyword;
        _disabledKeyword = disabledKeyword;
    }

    static bool IsPropertyTypeSuitable(MaterialProperty prop)
    {
        return prop.propertyType == UnityEngine.Rendering.ShaderPropertyType.Float || prop.propertyType == UnityEngine.Rendering.ShaderPropertyType.Range || prop.propertyType == UnityEngine.Rendering.ShaderPropertyType.Int;
    }

    public override float GetPropertyHeight(MaterialProperty prop, string label, MaterialEditor editor)
    {
        if (!IsPropertyTypeSuitable(prop))
        {
            return EditorGUIUtility.singleLineHeight * 2.5f;
        }

        return base.GetPropertyHeight(prop, label, editor);
    }

    public override void OnGUI(Rect position, MaterialProperty prop, GUIContent label, MaterialEditor editor)
    {
        if (!IsPropertyTypeSuitable(prop))
        {
            GUIContent c = EditorGUIUtility.TrTextContentWithIcon("EnumToggle used on a non-suitable property: " + prop.name,
                MessageType.Warning);
            EditorGUI.LabelField(position, c, EditorStyles.helpBox);
            return;
        }

        if (prop.propertyType != UnityEngine.Rendering.ShaderPropertyType.Int)
        {
            // Is a float or a range property
            EditorGUI.BeginChangeCheck();

            EditorGUI.showMixedValue = prop.hasMixedValue;
            var value = (int)prop.floatValue;
            value = EditorGUI.Popup(position, label, value, _keywordsToChooseFrom);
            EditorGUI.showMixedValue = false;
            if (EditorGUI.EndChangeCheck())
            {
                prop.floatValue = value;
                SetChosenKeyword(prop, value);
            }
        }
        else
        {
            EditorGUI.BeginChangeCheck();

            EditorGUI.showMixedValue = prop.hasMixedValue;
            var value = prop.intValue;
            value = EditorGUI.Popup(position, label, value, _keywordsToChooseFrom);
            EditorGUI.showMixedValue = false;
            if (EditorGUI.EndChangeCheck())
            {
                prop.intValue = value;
                SetChosenKeyword(prop, value);
            }
        }
    }

    public override void Apply(MaterialProperty prop)
    {
        base.Apply(prop);
        if (!IsPropertyTypeSuitable(prop))
        {
            return;
        }

        if (prop.hasMixedValue)
        {
            return;
        }

        if (prop.propertyType != UnityEngine.Rendering.ShaderPropertyType.Int)
        {
            SetChosenKeyword(prop, (int)prop.floatValue);
        }
        else
        {
            SetChosenKeyword(prop, prop.intValue);
        }
    }

    private void SetChosenKeyword(MaterialProperty prop, int index)
    {
        if (_keywordsToChooseFrom.Length == 0)
        {
            return;
        }

        for (int i = 0; i < _keywordsToChooseFrom.Length; ++i)
        {
            // Is the keyword we are enabling or disabling the "none" keyword?
            bool choseDisabledKeyword = _keywordsToChooseFrom[i].text == _disabledKeyword;
            string keywordName = GetKeywordName(prop.name, _keywordsToChooseFrom[i].text);
            foreach (Material material in prop.targets)
            {
                if (index == i)
                {
                    material.EnableKeyword(keywordName);

                    // If this is enabling the "disabled keyword"
                    // then disable the "enabled keyword"
                    if (choseDisabledKeyword)
                    {
                        material.DisableKeyword(_enabledKeyword);
                    }
                }
                else
                {
                    material.DisableKeyword(keywordName);

                    // If this is disabling the "disabled keyword"
                    // then enable the "enabled keyword"
                    if (choseDisabledKeyword)
                    {
                        material.EnableKeyword(_enabledKeyword);
                    }
                }
            }
        }
    }

    // Final keyword name: property name + "_" + display name. Uppercased,
    // and spaces replaced with underscores.
    private static string GetKeywordName(string propName, string name)
    {
        string n = propName + "_" + name;
        return n.Replace(' ', '_').ToUpperInvariant();
    }
}
