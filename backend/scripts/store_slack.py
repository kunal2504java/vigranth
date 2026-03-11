"""Store Slack bot token in platform_credentials."""
import psycopg2
import os
from backend.core.security import encrypt_token

conn = psycopg2.connect(os.environ["DATABASE_URL_SYNC"])
cur = conn.cursor()

USER_ID = "e8167916-6f94-4577-bb9a-d93d917176a0"
BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
TEAM_ID = "T0AJY5LKSVC"
enc_token = encrypt_token(BOT_TOKEN)

cur.execute(
    "SELECT id FROM platform_credentials WHERE user_id = %s AND platform = %s",
    (USER_ID, "slack"),
)
row = cur.fetchone()

if row:
    cur.execute(
        "UPDATE platform_credentials SET access_token = %s, platform_user_id = %s, updated_at = NOW() WHERE id = %s",
        (enc_token, TEAM_ID, str(row[0])),
    )
    print("Updated existing Slack credentials")
else:
    cur.execute(
        """INSERT INTO platform_credentials
           (id, user_id, platform, access_token, platform_user_id, scopes, created_at, updated_at)
           VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, NOW(), NOW())""",
        (USER_ID, "slack", enc_token, TEAM_ID, "channels:history,im:history,chat:write,users:read"),
    )
    print("Inserted new Slack credentials")

conn.commit()

cur.execute(
    "SELECT platform, platform_user_id FROM platform_credentials WHERE user_id = %s",
    (USER_ID,),
)
for r in cur.fetchall():
    print(f"  Connected: {r[0]} (id={r[1]})")

cur.close()
conn.close()
print("Done!")
