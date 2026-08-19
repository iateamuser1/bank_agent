"""HTML for the mock bank portals, kept as Jinja2 string templates.

The five login variants differ only in *where the form lives*, which is the whole point of
the exercise. Field ids/names/autocomplete are realistic so the detector has honest signal.
"""

from jinja2 import DictLoader, Environment

_BASE = """
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ bank.name }}</title>
<style>
  body{font-family:system-ui,Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0}
  header{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;background:#1e293b}
  .brand{font-weight:700;font-size:20px;color:#38bdf8}
  main{max-width:820px;margin:40px auto;padding:0 20px}
  .card{background:#1e293b;border-radius:12px;padding:24px;max-width:380px}
  .center{margin:60px auto}
  label{display:block;margin:12px 0 4px;font-size:14px}
  input{width:100%;padding:10px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0}
  button,.btn{margin-top:16px;padding:10px 16px;border:0;border-radius:8px;background:#22c55e;color:#04210f;font-weight:700;cursor:pointer}
  .link{color:#38bdf8;background:none;font-weight:600}
  .err{color:#f87171;margin-top:10px}
  .modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center}
  .modal.open{display:flex}
  table{width:100%;border-collapse:collapse;margin-top:16px}
  td,th{border:1px solid #334155;padding:8px;text-align:left}
  iframe{width:400px;height:320px;border:0;border-radius:12px}
</style></head><body>
<header>
  <span class="brand">{{ bank.name }}</span>
  {% block header_right %}{% endblock %}
</header>
<main>{% block main %}{% endblock %}</main>
{% block extra %}{% endblock %}
</body></html>
"""

# Reusable form fragment (username + password).
_FORM = """
<form method="post" action="{{ base }}login" id="loginForm">
  <label for="username">Email</label>
  <input id="username" name="username" type="email" autocomplete="username" placeholder="you@example.com">
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Password">
  <button type="submit">Sign In</button>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
</form>
"""

# V1 — login sits in the header.
_INLINE_TOP = """
{% extends "base" %}
{% block header_right %}
  <form method="post" action="{{ base }}login" style="display:flex;gap:8px;align-items:end">
    <input name="username" type="email" autocomplete="username" placeholder="Email" style="width:150px">
    <input name="password" type="password" autocomplete="current-password" placeholder="Password" style="width:130px">
    <button type="submit">Sign In</button>
  </form>
{% endblock %}
{% block main %}
  <h1>Welcome to {{ bank.name }}</h1>
  <p>Online banking. Sign in from the top-right to view your statements.</p>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
{% endblock %}
"""

# V2 — centered login card.
_CENTER_CARD = """
{% extends "base" %}
{% block main %}
  <div class="card center">
    <h2>Sign in to {{ bank.name }}</h2>
    """ + _FORM + """
  </div>
{% endblock %}
"""

# V3 — login hidden in a modal behind a button.
_MODAL = """
{% extends "base" %}
{% block header_right %}<button class="btn" onclick="document.getElementById('m').classList.add('open')">Login</button>{% endblock %}
{% block main %}
  <h1>{{ bank.name }}</h1>
  <p>Click <strong>Login</strong> to access your account.</p>
{% endblock %}
{% block extra %}
  <div class="modal" id="m"><div class="card">
    <h2>Sign in</h2>
    """ + _FORM + """
  </div></div>
{% endblock %}
"""

# V4a — two-step: username first.
_TWO_STEP = """
{% extends "base" %}
{% block main %}
  <div class="card center">
    <h2>Sign in to {{ bank.name }}</h2>
    <form method="post" action="{{ base }}login">
      <label for="username">Email</label>
      <input id="username" name="username" type="email" autocomplete="username" placeholder="you@example.com">
      <button type="submit">Next</button>
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
    </form>
  </div>
{% endblock %}
"""

# V4b — two-step: password second.
_TWO_STEP_PW = """
{% extends "base" %}
{% block main %}
  <div class="card center">
    <h2>Enter your password</h2>
    <p>{{ username }}</p>
    <form method="post" action="{{ base }}login-password">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Password">
      <button type="submit">Sign In</button>
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
    </form>
  </div>
{% endblock %}
"""

# V5 — login form embedded via an iframe.
_IFRAME_HOME = """
{% extends "base" %}
{% block main %}
  <h1>{{ bank.name }}</h1>
  <p>Sign in below.</p>
  <iframe src="{{ base }}login-frame" title="Sign in"></iframe>
{% endblock %}
"""

_IFRAME_FRAME = """
<!doctype html><html><head><meta charset="utf-8"><style>
  body{font-family:system-ui,Arial;background:#1e293b;color:#e2e8f0;margin:0;padding:16px}
  label{display:block;margin:10px 0 4px}
  input{width:100%;padding:9px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e2e8f0}
  button{margin-top:14px;padding:10px 16px;border:0;border-radius:8px;background:#22c55e;color:#04210f;font-weight:700}
  .err{color:#f87171;margin-top:8px}
</style></head><body>
""" + _FORM + """
</body></html>
"""

_OTP = """
{% extends "base" %}
{% block main %}
  <div class="card center">
    <h2>Verify it's you</h2>
    <p>We emailed a 6-digit code to {{ email }}.</p>
    <form method="post" action="{{ base }}otp">
      <label for="otp">Verification code</label>
      <input id="otp" name="otp" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="123456">
      <button type="submit">Verify</button>
      {% if error %}<div class="err">{{ error }}</div>{% endif %}
    </form>
  </div>
{% endblock %}
"""

_STATEMENTS = """
{% extends "base" %}
{% block header_right %}<a class="link" href="{{ base }}logout">Log out</a>{% endblock %}
{% block main %}
  <h1>Your statements</h1>
  <p>Signed in as {{ username }}. Download a statement below.</p>
  <table>
    <tr><th>Period</th><th>Date</th><th>Download</th></tr>
    {% for s in statements %}
    <tr>
      <td>{{ s.period }}</td>
      <td data-stmt-date="{{ s.stmt_date }}">{{ s.stmt_date }}</td>
      <td><a class="link" href="{{ base }}statement/{{ s.id }}.pdf" data-download="statement">Download PDF</a></td>
    </tr>
    {% endfor %}
  </table>
{% endblock %}
"""

_ENV = Environment(loader=DictLoader({
    "base": _BASE,
    "inline_top": _INLINE_TOP,
    "center_card": _CENTER_CARD,
    "modal": _MODAL,
    "two_step": _TWO_STEP,
    "two_step_pw": _TWO_STEP_PW,
    "iframe": _IFRAME_HOME,
    "iframe_frame": _IFRAME_FRAME,
    "otp": _OTP,
    "statements": _STATEMENTS,
}), autoescape=True)


def render(name: str, **ctx) -> str:
    return _ENV.get_template(name).render(**ctx)
