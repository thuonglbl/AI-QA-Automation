with open("frontend/src/components/admin/AdminDashboard.tsx", encoding="utf-8") as f:
    content = f.read()

# 1. Imports
content = content.replace(
    'import { BROWSER_TIMEZONE, TIMEZONE_OPTIONS } from "@/lib/timezone";',
    'import { BROWSER_TIMEZONE, TIMEZONE_OPTIONS } from "@/lib/timezone";\nimport { LANGUAGE_OPTIONS } from "@/lib/language";',
)

# 2. State variables
content = content.replace(
    "  const [createUserTimezone, setCreateUserTimezone] =\n    useState<string>(BROWSER_TIMEZONE);",
    '  const [createUserTimezone, setCreateUserTimezone] =\n    useState<string>(BROWSER_TIMEZONE);\n  const [createUserConversationLanguage, setCreateUserConversationLanguage] = useState("en");',
)

content = content.replace(
    "  const [editUserTimezone, setEditUserTimezone] =\n    useState<string>(BROWSER_TIMEZONE);",
    '  const [editUserTimezone, setEditUserTimezone] =\n    useState<string>(BROWSER_TIMEZONE);\n  const [editUserConversationLanguage, setEditUserConversationLanguage] = useState("en");',
)

# 3. create user payload
content = content.replace(
    "        role: createUserRole,\n        timezone: createUserTimezone,",
    "        role: createUserRole,\n        timezone: createUserTimezone,\n        conversation_language: createUserConversationLanguage,",
)
content = content.replace(
    '      setCreateUserTimezone(BROWSER_TIMEZONE);\n      setCreateUserProjectId("");',
    '      setCreateUserTimezone(BROWSER_TIMEZONE);\n      setCreateUserConversationLanguage("en");\n      setCreateUserProjectId("");',
)

# 4. start editing user
content = content.replace(
    "    setEditUserTimezone(u.timezone || BROWSER_TIMEZONE);\n    setEditUserIsActive(u.is_active);",
    '    setEditUserTimezone(u.timezone || BROWSER_TIMEZONE);\n    setEditUserConversationLanguage(u.conversation_language || "en");\n    setEditUserIsActive(u.is_active);',
)

# 5. edit user payload
content = content.replace(
    "        role: editUserRole,\n        timezone: editUserTimezone,\n        is_active: editUserIsActive,",
    "        role: editUserRole,\n        timezone: editUserTimezone,\n        conversation_language: editUserConversationLanguage,\n        is_active: editUserIsActive,",
)

# 6. create user UI
create_tz_ui = """                  <div>
                    <Label
                      htmlFor="create-user-timezone"
                      className="text-slate-700 block"
                    >
                      Timezone
                    </Label>
                    <select
                      id="create-user-timezone"
                      aria-label="Timezone"
                      value={createUserTimezone}
                      onChange={(e) => setCreateUserTimezone(e.target.value)}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <option key={tz} value={tz}>
                          {tz}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-500 mt-1">
                      Message times are shown to this user in this timezone.
                    </p>
                  </div>"""

create_lang_ui = """                  <div>
                    <Label
                      htmlFor="create-user-language"
                      className="text-slate-700 block"
                    >
                      Language
                    </Label>
                    <select
                      id="create-user-language"
                      aria-label="Language"
                      value={createUserConversationLanguage}
                      onChange={(e) => setCreateUserConversationLanguage(e.target.value)}
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    >
                      {LANGUAGE_OPTIONS.map((lang) => (
                        <option key={lang.value} value={lang.value}>
                          {lang.label}
                        </option>
                      ))}
                    </select>
                  </div>"""

content = content.replace(create_tz_ui, create_tz_ui + "\n" + create_lang_ui)


# 7. edit user UI
edit_tz_ui = """                              <div>
                                <Label
                                  htmlFor={`edit-user-timezone-${u.id}`}
                                  className="text-slate-700 block"
                                >
                                  Timezone
                                </Label>
                                <select
                                  id={`edit-user-timezone-${u.id}`}
                                  aria-label={`Timezone for ${u.display_name}`}
                                  value={editUserTimezone}
                                  onChange={(e) =>
                                    setEditUserTimezone(e.target.value)
                                  }
                                  className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                                >
                                  {TIMEZONE_OPTIONS.map((tz) => (
                                    <option key={tz} value={tz}>
                                      {tz}
                                    </option>
                                  ))}
                                </select>
                              </div>"""

edit_lang_ui = """                              <div>
                                <Label
                                  htmlFor={`edit-user-language-${u.id}`}
                                  className="text-slate-700 block"
                                >
                                  Language
                                </Label>
                                <select
                                  id={`edit-user-language-${u.id}`}
                                  aria-label={`Language for ${u.display_name}`}
                                  value={editUserConversationLanguage}
                                  onChange={(e) =>
                                    setEditUserConversationLanguage(e.target.value)
                                  }
                                  className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                                >
                                  {LANGUAGE_OPTIONS.map((lang) => (
                                    <option key={lang.value} value={lang.value}>
                                      {lang.label}
                                    </option>
                                  ))}
                                </select>
                              </div>"""

content = content.replace(edit_tz_ui, edit_tz_ui + "\n" + edit_lang_ui)

# 8. User list UI
user_list_tz_ui = """                                {u.timezone && (
                                  <span
                                    className="inline-flex px-2 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700"
                                    title="User's timezone (message times localized to this)"
                                  >
                                    {u.timezone}
                                  </span>
                                )}"""

user_list_lang_ui = """                                {u.conversation_language && (
                                  <span
                                    className="inline-flex px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-50 text-indigo-700"
                                    title="User's preferred conversation language"
                                  >
                                    {LANGUAGE_OPTIONS.find(l => l.value === u.conversation_language)?.label || u.conversation_language}
                                  </span>
                                )}"""

content = content.replace(user_list_tz_ui, user_list_tz_ui + "\n" + user_list_lang_ui)

with open("frontend/src/components/admin/AdminDashboard.tsx", "w", encoding="utf-8") as f:
    f.write(content)
