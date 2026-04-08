/**
 * Simple shared-secret auth.
 * The React Native app sends the secret in every request header.
 * This is enough security for a personal/hobby backend — if you ever
 * go commercial and multi-user, swap this for JWT or Supabase Auth.
 */
function authMiddleware(req, res, next) {
  const secret = process.env.API_SECRET;

  // If no secret is configured, skip auth (dev mode)
  if (!secret || secret === 'replace-with-your-random-secret') {
    console.warn('[AUTH] Warning: API_SECRET not set. Running without auth.');
    return next();
  }

  const provided = req.headers['x-api-secret'];

  if (!provided) {
    return res.status(401).json({ error: 'Missing x-api-secret header' });
  }

  if (provided !== secret) {
    return res.status(403).json({ error: 'Invalid API secret' });
  }

  next();
}

module.exports = { authMiddleware };