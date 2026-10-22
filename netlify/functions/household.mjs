// Shared purchase for a household (live sharing between two phones).
// GET  /api/household?code=XXXX  -> { state, updatedAt }   (404 if the code does not exist)
// PUT  /api/household?code=XXXX  body { state, ifMatch }   -> { state, updatedAt }   (state is encrypted by the phones; 409 if someone saved in between)
// DELETE /api/household?code=XXXX                         -> removes the shared purchase from the server
// GET  /api/household?ping=1     -> { ok: true }           (lets the app know sharing is available)
// The code is a random 9-character key that only the two of you know; there are no accounts.
// v2: the phones send a record id derived from the share code (never the code itself) and a write token
// (header x-maftech-w); the server keeps only a hash of the token and refuses changes without it.
import { getStore } from "@netlify/blobs";
import { handle } from "../lib/household-core.mjs";

export default async (req) => handle(req, getStore({ name: "households", consistency: "strong" }));

export const config = { path: "/api/household" };
