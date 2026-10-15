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
using UnityEngine;

namespace Oculus.Avatar2
{
    /**
     * This file contains two attributes: CollapsibleSectionStartAttribute and CollapsibleSectionEndAttribute.
     * These attributes are used to create collapsible sections in the Unity Inspector to organize serialized fields.
     *
     * Usage Example:
     * [CollapsibleSectionStart("Section Title")]
     * public int someVariable;
     * [CollapsibleSectionEnd]
     * public int endVariable;
     */
    [AttributeUsage(AttributeTargets.Field)]
    public class CollapsibleSectionStartAttribute : PropertyAttribute
    {
        public readonly string SectionTitle;
        public readonly bool StartCollapsed;    // whether the section starts collapsed
        public readonly Color TextColor;        // color of the section header

        public CollapsibleSectionStartAttribute(string sectionTitle, bool startCollapsed = false, float r = 1f, float g = 1f, float b = 1f)
        {
            SectionTitle = sectionTitle;
            StartCollapsed = startCollapsed;
            TextColor = new Color(r, g, b);
        }
    }

    // Attribute for marking the end of the dropdown.
    // This is intentionally left empty, because the presence of it only shows the ending to a section,
    // and doesn't have any other properties. If this attribute is not used after "CollapsibleSectionStart",
    // all fields after section start will be included in the section.
    [AttributeUsage(AttributeTargets.Field)]
    public class CollapsibleSectionEndAttribute : PropertyAttribute
    {
    }
}
