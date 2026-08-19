/**
 * Adds a "▶ Run Scan Now" menu item to the bound Google Sheet. Clicking it
 * triggers the daily_scan.yml GitHub Actions workflow via workflow_dispatch,
 * so the operator never needs to open GitHub.
 *
 * Setup:
 *   1. In the Sheet: Extensions > Apps Script, paste this file's contents.
 *   2. Project Settings > Script Properties, add:
 *        GITHUB_OWNER   = <github username or org>
 *        GITHUB_REPO    = <repo name>
 *        GITHUB_TOKEN   = <fine-grained PAT, scoped to Actions: write on this repo only>
 *        GITHUB_WORKFLOW_FILE = daily_scan.yml
 *   3. Reload the Sheet; the "▶ Run Scan Now" menu should appear.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Follower Tracker')
    .addItem('▶ Run Scan Now', 'runScanNow')
    .addToUi();
}

function runScanNow() {
  const props = PropertiesService.getScriptProperties();
  const owner = props.getProperty('GITHUB_OWNER');
  const repo = props.getProperty('GITHUB_REPO');
  const token = props.getProperty('GITHUB_TOKEN');
  const workflowFile = props.getProperty('GITHUB_WORKFLOW_FILE') || 'daily_scan.yml';

  if (!owner || !repo || !token) {
    SpreadsheetApp.getUi().alert(
      'Missing setup: set GITHUB_OWNER, GITHUB_REPO, and GITHUB_TOKEN in ' +
      'Project Settings > Script Properties before using this button.'
    );
    return;
  }

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflowFile}/dispatches`;
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
    },
    payload: JSON.stringify({ ref: 'master' }),
    muteHttpExceptions: true,
  });

  const status = response.getResponseCode();
  if (status === 204) {
    SpreadsheetApp.getActiveSpreadsheet().toast('Scan triggered — check the Log tab shortly.', 'Follower Tracker');
  } else {
    SpreadsheetApp.getUi().alert(`Failed to trigger scan (HTTP ${status}): ${response.getContentText()}`);
  }
}
