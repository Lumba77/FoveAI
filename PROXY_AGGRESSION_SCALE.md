# Proxy Aggression Scale — Standardized

## Standardized 1-5 Scale

**Higher number = MORE aggressive compression**

| Level | Name | Multiplier | Description |
|-------|------|------------|-------------|
| 0 | Auto | Auto | Model-detected based on context window |
| 1 | Minimal | x0.5 | Very light compression, preserves most context |
| 2 | Light | x1.0 | Gentle compression, balanced approach |
| 3 | Moderate | x2.0 | Standard compression, good balance |
| 4 | Aggressive | x4.0 | Heavy compression, for large contexts |
| 5 | Maximum | x8.0 | Maximum compression, minimal context |

## Usage in Code

**server.js** - Foveation override:
```javascript
const aggressionMap = { 1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0, 5: 8.0 };
```

**model-profiles.json** - Per-model settings:
```json
{
  "proxy_aggression": 3  // Moderate compression
}
```

**.env** - Global override:
```env
XRLF_PROXY_AGGRESSION=3
```

## Important Notes

- **Scale is consistent** across all code files
- **Higher = MORE aggressive** (intuitive)
- **4 = Aggressive** (heavy compression, not light)
- **2 = Light** (gentle, not worst case)
- All values should be in range 0-5 (0 = auto)
