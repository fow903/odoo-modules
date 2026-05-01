# Admin-Managed MCP Key Creation — Migration Guide (v18 → v17)

## Overview

These changes restrict MCP key management to administrators and allow them to create
keys on behalf of any user. Previously, any internal user could create and delete their
own keys. Now only `base.group_system` users can do so.

---

## 1. `wizards/generate_key.py`

**Add `user_id` field** so the wizard targets a specific user instead of always the
current session user.

```python
# Before
def action_make_key(self):
    ...
    key_model.sudo().create({
        'name': self.name,
        'user_id': self.env.uid,   # always the logged-in admin
        ...
    })
```

```python
# After — add this field to the class body
user_id = fields.Many2one(
    comodel_name='res.users',
    string="User",
    required=True,
    default=lambda self: self.env.user,
)

# And update action_make_key
def action_make_key(self):
    ...
    key_model.sudo().create({
        'name': self.name,
        'user_id': self.user_id.id,   # explicit target user
        ...
    })
```

---

## 2. `models/res_users.py`

**Pass `default_user_id` context** when opening the wizard from the user form so the
wizard pre-selects the user whose form is open.

```python
# Before
@check_identity
def action_generate_mcp_key(self):
    return {
        ...
        'context': {},
    }
```

```python
# After
@check_identity
def action_generate_mcp_key(self):
    return {
        ...
        'context': {'default_user_id': self.id},
    }
```

---

## 3. `views/generate_key.xml`

**Add `user_id` field** to the wizard form so the admin can see and change the target
user.

```xml
<!-- After name field, before scope -->
<field name="user_id"/>
```

---

## 4. `views/res_users.xml`

Two changes:

**a) Correct the inherited view reference** (v17 note: verify the right `inherit_id`
and `xpath` for v17 — the target page name may differ).

| v18 value | Check in v17 |
|-----------|-------------|
| `inherit_id` → `base.view_users_form` | May still be `base.view_users_form_simple_modif` |
| xpath `//page[@name='account_security']` | May be a different `@name` |

**b) Restrict the "Add MCP Key" button to admins:**

```xml
<!-- Before -->
<button name="action_generate_mcp_key" string="Add MCP Key" type="object"
        class="btn btn-secondary"/>

<!-- After -->
<button name="action_generate_mcp_key" string="Add MCP Key" type="object"
        class="btn btn-secondary" groups="base.group_system"/>
```

---

## 5. `views/key.xml`

**Restrict the Delete button** in the kanban card to admins:

```xml
<!-- Before -->
<button name="unlink" type="object" string="Delete"
        class="btn btn-secondary ms-auto my-auto"/>

<!-- After -->
<button name="unlink" type="object" string="Delete"
        class="btn btn-secondary ms-auto my-auto" groups="base.group_system"/>
```

---

## 6. `security/ir.model.access.csv`

Three access rules change:

| Line id | What changed |
|---------|-------------|
| `access_muk_mcp_key_user` | `perm_write`, `perm_create`, `perm_unlink` → `0` (users can only read their own keys) |
| `access_muk_mcp_generate_key` | Group changed from `base.group_user` to `base.group_system` |
| `access_muk_mcp_key_show` | Group changed from `base.group_user` to `base.group_system` |

```csv
# Before
access_muk_mcp_key_user,access_muk_mcp_key_user,model_muk_mcp_key,base.group_user,1,1,1,1
access_muk_mcp_generate_key,access_muk_mcp_generate_key,model_muk_mcp_generate_key,base.group_user,1,0,1,1
access_muk_mcp_key_show,access_muk_mcp_key_show,model_muk_mcp_key_show,base.group_user,1,0,1,0

# After
access_muk_mcp_key_user,access_muk_mcp_key_user,model_muk_mcp_key,base.group_user,1,0,0,0
access_muk_mcp_generate_key,access_muk_mcp_generate_key,model_muk_mcp_generate_key,base.group_system,1,0,1,1
access_muk_mcp_key_show,access_muk_mcp_key_show,model_muk_mcp_key_show,base.group_system,1,0,1,0
```

---

## v17-specific notes

- The wizard model name (`muk_mcp.generate_key`) and key model name (`muk_mcp.key`)
  are unchanged — no rename needed.
- `@check_identity` decorator on `action_generate_mcp_key` requires
  `odoo.addons.base.models.res_users.check_identity`. Verify it exists in v17; if not,
  remove the decorator.
- The `scope` field values (`read` / `write`) map to **Read Only** and **Read & Write**
  — these control whether the token can call write/action tools. No change needed there.
- Test that `key_model.sudo().create(...)` in the wizard still bypasses record rules in
  v17 the same way it does in v18.
