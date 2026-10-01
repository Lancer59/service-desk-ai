---
name: notification_skill
domain: notifications
description: Send notifications, emails, and major incident alerts to users and teams
trigger_keywords: [notify, notification, send email, email user, alert, major incident, outage, broadcast, inform, communicate, send message]
tools: [notify_user, send_email, send_major_incident_notification]
---

# Notification Skill

You help send messages, emails, and incident alerts to users and teams.

## General rules

- Always confirm the recipient and message content before sending.
- Use `notify_user` for quick in-platform notifications.
- Use `send_email` for formal or detailed communications.
- Use `send_major_incident_notification` only for confirmed P1/P2 major incidents.

---

## notify_user

**When to use:** Send a short notification or update to a user via the chat/bot platform.

**Collect:** `message`, `user_email`. Optionally `channel_id` if targeting a specific channel.

---

## send_email

**When to use:** Send a formal email — ticket confirmations, follow-ups, detailed instructions.

**Collect:** `to` (email), `subject`, `body`.

---

## send_major_incident_notification

**When to use:** A confirmed major incident (P1/P2) affects multiple users and requires broadcast notification.

**Collect:** `ticket_number`, `domain`, `short_description`, `description`, `priority`, `status`.

**Warning:** Only use for verified major incidents. Confirm with the user before broadcasting.
