Analyze this game idea and extract structured requirements:

**Game Idea:** {{ idea }}

{% if previous_answers %}
**Previous Clarifications:**
{% for qa in previous_answers %}
- Q: {{ qa.question }}
  A: {{ qa.answer }}
{% endfor %}
{% endif %}

Extract:
- genre, title, description
- all entities with their properties and behaviors
- control scheme (key mappings)
- win/lose conditions
- visual style preferences
- scoring mechanics

For any information not explicitly stated, create an Assumption with:
- dimension: which aspect it covers
- value: your best guess
- confidence: 0.0–1.0

Rate your overall confidence (0.0–1.0) that the requirements are complete enough to build from.
