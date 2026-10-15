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

using System.Collections.Generic;
using UnityEngine;
using UnityEditor;
// ReSharper disable HeapView.ObjectAllocation.Evident

// ReSharper disable once ClassNeverInstantiated.Global
public sealed class KeywordProxyDrawer : MaterialPropertyDrawer
{
    private static List<KeywordProxyDrawer>? s_instances;

    private readonly string _originalValue;
    private readonly string[] _proxyValues;

    public KeywordProxyDrawer(string name1, string name2)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2 };
        AddToInstances(this);
    }

    public KeywordProxyDrawer(string name1, string name2, string name3)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3 };
        AddToInstances(this);
    }
    public KeywordProxyDrawer(string name1, string name2, string name3, string name4)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3, name4 };
        AddToInstances(this);
    }

    public KeywordProxyDrawer(string name1, string name2, string name3, string name4, string name5)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3, name4, name5 };
        AddToInstances(this);
    }

    public KeywordProxyDrawer(string name1, string name2, string name3, string name4, string name5, string name6)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3, name4, name5, name6 };
        AddToInstances(this);
    }

    public KeywordProxyDrawer(string name1, string name2, string name3, string name4, string name5, string name6, string name7)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3, name4, name5, name6, name7 };
        AddToInstances(this);
    }

    public KeywordProxyDrawer(string name1, string name2, string name3, string name4, string name5, string name6, string name7, string name8)
    {
        _originalValue = name1;
        _proxyValues = new[] { name2, name3, name4, name5, name6, name7, name8 };
        AddToInstances(this);
    }

    ~KeywordProxyDrawer()
    {
        RemoveFromInstances(this);
    }

    private static void AddToInstances(KeywordProxyDrawer p)
    {
        s_instances ??= new List<KeywordProxyDrawer>();
        s_instances.Add(p);
    }

    private static void RemoveFromInstances(KeywordProxyDrawer p)
    {
        s_instances?.Remove(p);
    }

    // ReSharper disable once UnusedParameter.Local
    private bool IsKeywordEnabled(Material mat, string? proxyName)
    {
        foreach (var s in _proxyValues)
        {
            if (mat.IsKeywordEnabled(s))
            {
                return true;
            }
        }
        return false;
    }

    public static bool AreKeywordsEnabled(Material mat, string proxyName)
    {
        bool elementMatches = false;
        if (s_instances != null)
        {
            foreach (KeywordProxyDrawer p in s_instances)
            {
                elementMatches |= p.IsKeywordEnabled(mat, proxyName);
                if (elementMatches)
                {
                    break;
                }
            }
        }
        return elementMatches;
    }

    public override void OnGUI(Rect position, MaterialProperty prop, string label, MaterialEditor editor)
    {
        var elementMatches = false;
        foreach (Object? obj in prop.targets)
        {
            Material? m = obj as Material;
            if (m != null)
            {
                elementMatches |= IsKeywordEnabled(m, _originalValue);
                if (elementMatches)
                {
                    break;
                }
            }
        }

        EditorGUI.BeginDisabledGroup(true);
        EditorGUI.Toggle(position, label, elementMatches);
        EditorGUI.EndDisabledGroup();
    }
}
