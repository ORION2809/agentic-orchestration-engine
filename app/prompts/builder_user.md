{% if mode == "fresh" %}
Generate a complete, working HTML5 browser game based on this plan:

**Game Plan:**
```json
{{ plan_json }}
```

Generate these files:
{% for file in file_list %}
- `{{ file }}`
{% endfor %}

For each file, output the COMPLETE source code. Do not use placeholders or TODO comments.

The game must:
1. Run immediately when index.html is opened in a browser
2. Respond to keyboard input as specified in the controls
3. Keep and display score
4. Have a game-over condition
5. Support restart via 'R' key
6. Use `requestAnimationFrame` for the game loop
7. Expose state via `window.gameState`

{% elif mode == "repair" %}
The previous build has errors that must be fixed. Here is the current code and the issues found:

**Current Code:**
{% for filename, code in current_files.items() %}
### {{ filename }}
```
{{ code }}
```
{% endfor %}

**Issues to Fix:**
{% for issue in issues %}
- [{{ issue.severity }}] {{ issue.description }}{% if issue.file %} (in {{ issue.file }}{% if issue.line %}, line {{ issue.line }}{% endif %}){% endif %}
{% endfor %}

Fix ALL issues and output the complete corrected files. Do not introduce new problems.
Preserve all working functionality while fixing the issues.
{% endif %}
