---
name: sochen
description: When and how to hand jobs to Sochen (phone calls to businesses, long cloud jobs, email and calendar with the user's OK), check them, and make free GST invoices, rent receipts and UPI bill splits.
version: 0.2.1
author: Sochen
license: MIT
metadata:
  hermes:
    tags: [Sochen, Phone calls, Delegation, India, Invoices]
    related_skills: []
---

# Working with Sochen

Sochen (sochen.dev) is the user's cloud agent. It has things Hermes doesn't: a phone that calls US
businesses, its own computer that keeps working when this one sleeps, and the email, calendar and
other apps the user connected in Sochen. Anything that pays, books, sends or deletes waits for the
user's OK in the Sochen app, with the details shown first.

## When to hand a job to Sochen

Use `sochen_handoff` when the job needs one of those things:

- **A phone call**: opening hours, a price, whether something is in stock, a free table, a repair's
  status. Sochen says it's an AI calling for the user, and brings back the answer and a transcript.
- **A long job**: research, comparisons or browsing that takes many minutes, or should keep going
  after the user closes the laptop.
- **The user's Sochen apps**: reading or drafting email, finding a calendar slot. Sending waits for
  the user's OK.

Keep doing yourself what Hermes's own tools do well: files on this computer, code, the terminal, a
quick web search.

## Writing the job

Sochen acts on the words alone, so write complete instructions:

- Who: the business's name and phone number (with the country code), or the person or inbox.
- What: the exact question to ask or the thing to do.
- What to bring back: "their opening hours today and whether they take walk-ins".
- Limits: a deadline, a budget, "don't book, just ask".

Good: "Call Joe's Pizza at +1 415 555 0134. Ask if they're open until 11 tonight and whether they
deliver to 94110. Don't order anything. Bring back both answers."

Weak: "check the pizza place".

## After handing it off

- `answered`: give the user Sochen's answer and the chat link.
- `working`: tell the user it has started and you'll report back. Don't wait or poll in a loop:
  Hermes is told when the job finishes, on the user's next message. Check sooner only if they ask,
  with `sochen_job`.
- `needs_approval`: tell the user what Sochen is waiting for and that they approve it in the Sochen
  app or at the chat link. You can't approve it, and you shouldn't try to work around it.
- `needs_setup`: the user hasn't connected Sochen. Pass on the setup message as it is: a key from
  sochen.dev/hermes, then `hermes config set SOCHEN_API_KEY <key>`.
- A refusal with `upgrade_url` (for example, calls need paid API credits, or the 100 free credits are used):
  tell the user what Sochen said and give them the link.

Jobs use the user's Sochen API credits, apart from their Sochen app plan. Every account starts with
100 free API credits, spread over any number of jobs, then packs or a monthly API plan; replies carry `credits_left`, and `/sochen credits` shows what's left. Checking a job
or the desk costs nothing.

To follow up on a job ("now ask them about Saturday"), pass its `chat_id` to `sochen_handoff`.

## Free tools, no account

- `sochen_gst_invoice`: an Indian GST tax invoice as a PDF (CGST and SGST within a state, IGST
  across states), with a UPI QR when the seller gives a UPI ID.
- `sochen_rent_receipts`: monthly house rent receipts for an HRA claim, three to a page.
- `sochen_upi_split`: a shared bill split per person, with a UPI QR for each share.

Ask the user for details that are missing, like the invoice number or the landlord's name, rather
than inventing them. Each file's link works for 24 hours.

## The desk

`sochen_desk` (or `/sochen`) shows what waits for the user's OK, what's running and what finished
today. Use it when the user asks what Sochen is up to or what needs them.
