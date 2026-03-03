Create a detailed game plan from these requirements:

**Requirements:**
```json
{{ requirements_json }}
```

**Complexity Tier:** {{ complexity_tier }}
**Token Budget:** {{ token_budget }} tokens for the builder phase

{% if simplification_round > 0 %}
**SIMPLIFICATION ROUND {{ simplification_round }}:**
The previous plan was too complex (scored {{ previous_score }}/10).
Reduce complexity by:
- Fewer entities (max 3-4 types)
- Simpler physics (no acceleration, basic AABB)
- Fewer game states
- Remove non-essential features
{% endif %}

Produce a GamePlan with all required fields. Be specific about:
- Exact entity properties (x, y, width, height, speed, color)
- Exact key bindings
- Exact scoring values
- File names and their responsibilities
