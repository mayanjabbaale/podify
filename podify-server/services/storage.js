const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

let supabase = null;

function getClient() {
  if (!supabase) {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_KEY;

    if (!url || !key || url.includes('your-project')) {
      throw Object.assign(
        new Error('Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env'),
        { status: 503 }
      );
    }

    supabase = createClient(url, key);
  }
  return supabase;
}

const BUCKET = process.env.SUPABASE_BUCKET || 'podify-audio';

/**
 * Uploads a local audio file to Supabase Storage.
 * Returns the public URL.
 */
async function uploadAudio(localFilePath, destinationFileName) {
  const client = getClient();
  const fileBuffer = fs.readFileSync(localFilePath);

  const { error } = await client.storage
    .from(BUCKET)
    .upload(destinationFileName, fileBuffer, {
      contentType: 'audio/mpeg',
      upsert: false,
    });

  if (error) {
    throw Object.assign(
      new Error(`Storage upload failed: ${error.message}`),
      { status: 502 }
    );
  }

  const { data } = client.storage.from(BUCKET).getPublicUrl(destinationFileName);

  if (!data?.publicUrl) {
    throw Object.assign(new Error('Could not get public URL for uploaded file'), { status: 500 });
  }

  return data.publicUrl;
}

/**
 * Deletes a file from Supabase Storage.
 * Used for cleanup if something goes wrong after upload.
 */
async function deleteAudio(fileName) {
  const client = getClient();
  await client.storage.from(BUCKET).remove([fileName]);
}

module.exports = { uploadAudio, deleteAudio };