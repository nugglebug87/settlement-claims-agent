# Settlement Claim Form Helper

This unpacked Chrome/Edge extension fills ordinary text and numeric answers from a current reviewed claim packet. It does not click submission controls, sign, certify, select checkboxes or dropdowns, upload files, or bypass CAPTCHA. The administrator's page can save answers when input events run; filling requires explicit transmission authorization.

## Install and use

1. Sign in to the Settlement Claims workspace. Open a prepared claim in My claims or the approval queue, then download the browser helper ZIP from its review dialog.
2. Extract the ZIP into a folder you will keep. In Chrome open chrome://extensions, or in Edge open edge://extensions. Enable Developer mode, click Load unpacked, and choose the folder containing manifest.json. Pin the helper to the toolbar.
3. Keep the workspace claim review open and click the helper's toolbar icon. Choose Load claim from workspace. A prepared packet allows ordinary answer drafting; it is not approval to sign or submit.
4. Open the exact official form link in another tab. Open the helper on that tab and choose Inspect official form. Select each answer's destination and review the mapping against the page.
5. Authorize sending the selected answers, including any immediate autosave, then choose Fill selected answers. Review the result on the official site. Complete attachments, benefit choices, signatures, legal declarations, CAPTCHA, and submission yourself after the claim-specific review and approval.
6. Return to the workspace with the actual administrator confirmation. Filling never marks a claim submitted.

## Privacy and limits

- Only activeTab, scripting, and storage permissions are requested. No permanent host access, automatic content scripts, external messaging, remote code, or telemetry.
- The supported workspace origins are the existing production app and http://localhost:8000. A different deployment needs the reviewed origin added to popup.js.
- Session storage holds only a workspace tab ID, origin, claim ID, packet hash, and expiration. Answers are fetched into popup memory and never stored or synced by the extension. The reference becomes unusable after ten minutes and is cleared when next accessed, after filling, on Forget loaded claim, or when the browser session ends.
- Keep the workspace tab open and signed in. The helper revalidates the packet before inspection and before filling. Source/profile changes, expired claim windows, or confirmed submission block filling.
- Only visible, enabled ordinary input fields and textareas in the top document are supported. Iframes, shadow DOM, dropdowns, radio buttons, checkboxes, files, passwords, and credentials need manual completion.
- Sensitive/legal-field detection uses labels, descriptions, names, autocomplete, and fieldset legends. These checks are conservative heuristics; personally verify every destination. Unclear wording can require manual filling. Never map an ordinary answer to a field that signs or certifies a claim.
- The official URL must match exactly, including its query string (fragments are ignored). Redirects or multi-step destinations require reviewed URL correction and a fresh packet. The helper refuses to overwrite a different existing answer.
- Dynamic changes can produce partial filling. The helper reports uncertainty; the site may already have saved answers. Check the page before retrying.
- This package is for manual unpacked installation. It is not published in either browser's extension store and does not install itself.

## Development

Run npm install and npx playwright install chromium in this extension folder, then npm test. Runtime files have no npm dependencies. Tests use synthetic pages and never send a real claim. Chrome's activeTab documentation: https://developer.chrome.com/docs/extensions/develop/concepts/activeTab
