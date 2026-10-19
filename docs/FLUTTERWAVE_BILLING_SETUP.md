# Qwantej Pro billing setup

Qwantej Pro is a card-only recurring subscription at **MWK 20,000 per month**. The checkout button stays disabled until the server has the Flutterwave API key, webhook hash, and matching monthly plan ID.

## Configure Flutterwave

Create a Flutterwave payment plan with these exact terms:

- Name: `Qwantej Pro Monthly`
- Amount: `20000`
- Currency: `MWK`
- Interval: `monthly`
- Payment method: card (Flutterwave payment plans require cards)

Use a test-mode plan and test API key for acceptance checks. Copy the numeric plan ID from the same Flutterwave environment as the API key.

In Flutterwave Dashboard → Settings → Webhooks, set the webhook URL to:

```text
https://<your-public-app-host>/api/v1/billing/webhook
```

Set a strong random secret hash there, and enable `charge.completed` and `subscription.cancelled` events. Put the same secret hash in the backend environment.

## Backend environment

Set these variables in the server environment (for Docker Compose, in the project `.env` file):

```text
FLUTTERWAVE_SECRET_KEY=<test-or-live-secret-key>
FLUTTERWAVE_SECRET_HASH=<same-random-webhook-hash>
FLUTTERWAVE_PRO_MONTHLY_PLAN_ID=<numeric-plan-id>
FLUTTERWAVE_PRO_MONTHLY_PRICE_MWK=20000
PUBLIC_APP_BASE_URL=https://<your-public-app-host>
```

Keep the secret key and webhook hash on the server. Never place either in frontend variables or commit their values. If the plan, key, and price do not match, payments will not grant Pro access.

## Verification behavior

The backend creates a checkout reference for the signed-in user. It grants Pro only after Flutterwave transaction verification confirms the reference, successful status, MWK currency, exact amount, and card payment type. Repeated notifications for one transaction are safe to process. A cancellation event removes Pro only when the billing flow granted that user's access; manual admin grants are preserved.

The return page checks the transaction with Flutterwave as a backup if the webhook is delayed. Customers can manage or cancel recurring card billing through Flutterwave's subscription emails. The current checkout does not offer recurring mobile-money billing.
