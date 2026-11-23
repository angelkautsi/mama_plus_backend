# MAMA+ FastAPI backend

## Run locally

From the project root, install the backend dependencies and configure
`backend/.env` with a private `JWT_SECRET_KEY`:

```bash
python -m pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Password recovery email also requires these settings in `backend/.env`:

```env
SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@example.org
FRONTEND_BASE_URL=http://localhost:3000
```

Use the SMTP credentials and frontend URL for the deployment environment.
Reset links expire after 30 minutes and can be used once.

Run the frontend in a second terminal. Its `/api` requests are forwarded to
FastAPI except for the AI companion endpoints, which are handled by the
frontend server.

On a new database, create the first administrator from the project root:

```bash
python -m backend.bootstrap_admin
```

The command prompts for credentials and refuses to create another bootstrap
administrator once one exists.

## API areas

- `/users`: patient registration, login, account profile, and deactivation.
- `/patients`, `/nurses`, `/facilities`: clinical roster, assignments, and facility directory.
- `/symptoms`, `/appointments`, `/medications`: patient records and nurse review/scheduling.
- `/messages`, `/alerts`, `/emergency-alerts`: secure care-team communication and triage alerts.
- `/kick-sessions`, `/contractions`: maternal tracking records.
- `/articles`: admin-managed educational content.
- `/admin/users`: administrator user creation, listing, and account status updates.
- `/admin/knowledge-rules`, `/ai-audits`, `/admin/ai-audits`: clinical knowledge directives and auditable AI interactions.
- `/system/activity`, `/admin/activity`, `/admin/reports`: operational activity history and administrator reports.

Clinical records require a bearer access token. Patients can access their own
records; nurses can access patients assigned to their nurse profile; admins
can manage system records. New SQLAlchemy tables are created automatically,
but existing databases are not migrated automatically.

Medication regimens are assigned and edited by nurses or admins. Patients can
view only their own active medications and update their dose-adherence records.

The first administrator creates the default MAMA+ facility during initial
sign-in if the database has no facilities. The app's predefined educational
articles and AI knowledge rules are also seeded when their backend collections
are empty.
