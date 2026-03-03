Review this generated game code against the plan:

**Game Plan:**
```json
{{ plan_json }}
```

**Generated Files:**
{% for filename, code in game_files.items() %}
### {{ filename }}
```{{ lang }}
{{ code }}
```
{% endfor %}

{% if deterministic_findings %}
**Automated Analysis Already Found:**
{% for finding in deterministic_findings %}
- [{{ finding.severity }}] {{ finding.description }}{% if finding.file %} ({{ finding.file }}{% if finding.line %}:{{ finding.line }}{% endif %}){% endif %}
{% endfor %}

Focus your review on issues the automated analysis might have MISSED, especially:
- Logic errors in game mechanics
- Missing features from the plan
- Edge cases in collision detection
- State management bugs
{% endif %}

Provide your findings as a CritiqueResult with:
- findings: list of CriticFinding objects
- compliance_score: float 0.0–1.0
- pass_result: boolean
