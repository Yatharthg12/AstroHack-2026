(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const csrf = $('meta[name="csrf-token"]')?.content || '';
  let context = {};
  try { context = JSON.parse(document.body.dataset.pageContext || '{}'); } catch (_) { context = {}; }

  const escapeText = value => String(value ?? '').replace(/[<>]/g, '');
  const formObject = form => {
    const fd = new FormData(form);
    const object = {};
    fd.forEach((value, key) => {
      if (key === 'csrf_token') return;
      if (key in object) object[key] = Array.isArray(object[key]) ? [...object[key], value] : [object[key], value];
      else object[key] = value;
    });
    $$('input[type="checkbox"]', form).forEach(input => { object[input.name] = input.checked; });
    return object;
  };
  async function fetchJSON(url, options = {}) {
    const headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (csrf) headers['X-CSRF-Token'] = csrf;
    if (options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body);
    }
    const response = await fetch(url, { credentials: 'same-origin', ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) { const error=new Error(data.message || data.error?.message || data.error || `Request failed (${response.status})`);error.status=response.status;throw error; }
    return data && data.ok === true && 'data' in data ? data.data : data;
  }
  function toast(message, type = 'success') {
    const region = $('[data-toasts]'); if (!region) return;
    const node = document.createElement('div'); node.className = `toast notice-${type}`; node.textContent = message;
    region.append(node); window.setTimeout(() => node.remove(), 4200);
  }
  function setBusy(form, busy, message = '') {
    form.classList.toggle('loading', busy);
    $$('button, input, textarea, select', form).forEach(el => el.disabled = busy);
    const status = $('[data-form-status]', form); if (status) status.textContent = message;
  }
  function download(content, type, filename) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 500);
  }
  function safeNumber(value, fallback = 0) { const n = Number(value); return Number.isFinite(n) ? n : fallback; }
  const motionBehavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';

  // Shared navigation and browser affordances.
  const header = $('[data-header]');
  const setHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 8);
  setHeader(); window.addEventListener('scroll', setHeader, { passive: true });
  const navToggle = $('[data-nav-toggle]'); const nav = $('[data-nav]');
  navToggle?.addEventListener('click', () => { const open = nav.classList.toggle('is-open'); navToggle.setAttribute('aria-expanded', String(open)); });
  $$('[data-nav-path]').forEach(link => { if (location.pathname.startsWith(link.dataset.navPath)) link.setAttribute('aria-current', 'page'); });
  $$('[data-range]').forEach(range => { const output = range.parentElement.querySelector('output'); const update = () => { if (output) output.value = range.value; }; range.addEventListener('input', update); update(); });
  $('[data-reload]')?.addEventListener('click', () => location.reload());

  // Onboarding: deterministic sun-sign disclosure, while normal HTML submission remains available.
  const birthDate = $('#birth_date');
  birthDate?.addEventListener('change', () => {
    const [, month, day] = birthDate.value.split('-').map(Number); if (!month || !day) return;
    const edge = [20,19,21,20,21,21,23,23,23,23,22,22];
    const signs = ['Capricorn','Aquarius','Pisces','Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio','Sagittarius','Capricorn'];
    const sign = day < edge[month - 1] ? signs[month - 1] : signs[month];
    const out = $('[data-sun-sign]'); if (out) out.textContent = `${sign} · derived only from the date range.`;
  });

  // Pulse: transparent deterministic reflection templates plus persistence.
  const pulseForm = $('[data-pulse-form]');
  const pulseTemplates = {
    low: ['A lower-energy day can still hold one useful choice. Make the next step smaller than your resistance.', 'Choose one task that takes under five minutes, then give yourself permission to pause.'],
    stretched: ['When several things compete for attention, clarity often begins by naming what can wait.', 'Write three demands down and circle only the one that truly needs you today.'],
    grounded: ['Steadiness can be a form of momentum. Name the smallest next move before asking yourself to see the whole path.', 'Write down one decision you can defer and one step you can complete in ten minutes.'],
    hopeful: ['Hope becomes useful when it has somewhere concrete to land. Protect it with one specific action.', 'Send one message or make one note that moves your focus forward.'],
    energised: ['Energy can open many doors at once. Choosing one direction may carry you further than starting five.', 'Give your best twenty minutes to one clearly named priority.']
  };
  pulseForm?.addEventListener('submit', async event => {
    event.preventDefault(); if (!pulseForm.reportValidity()) return;
    const payload = formObject(pulseForm);
    setBusy(pulseForm, true, 'Saving your check-in…');
    try {
      const data = await fetchJSON('/api/check-ins', { method: 'POST', body: payload });
      $('[data-reflection]').textContent = data.reflection;
      $('[data-micro-action]').textContent = data.micro_action;
      $('[data-reflection-why]').textContent = data.reason;
      const reflectionTag = $('[data-reflection-tag]');
      if (reflectionTag) reflectionTag.textContent = data.saved ? 'Latest saved reflection' : 'Unsaved reflection';
      pulseForm.dataset.checkinId = data.id || data.checkin_id || '';
      $$('[data-feedback]').forEach(button=>{button.disabled=!pulseForm.dataset.checkinId;});
      if (data.saved && Array.isArray(data.weekly)) {
        const streak = safeNumber(data.streak, 0);
        const streakLabel = $('[data-streak-label]');
        if (streakLabel) streakLabel.textContent = `This week · ${streak} day streak`;
        const eyebrow = $('[data-pulse-eyebrow]');
        if (eyebrow) eyebrow.textContent = streak > 0 ? `Day ${streak} in your rhythm` : 'Start your rhythm';
        $$('[data-week-day]').forEach((day, index) => {
          const done = Boolean(data.weekly[index]);
          day.classList.toggle('done', done);
          day.classList.toggle('today', !done && day.dataset.today === 'true');
          const marker = $('i', day);
          if (marker) marker.textContent = done ? '✓' : String(index + 1);
        });
      }
      setBusy(pulseForm, false, payload.save ? 'Saved privately to your Journey.' : 'Reflection created without saving.'); toast('Today’s Pulse is ready.');
    } catch (error) { setBusy(pulseForm, false, `Could not create or save this reflection: ${error.message}`); }
  });
  $$('[data-feedback]').forEach(button => button.addEventListener('click', async () => {
    const group = button.parentElement;
    const id = pulseForm?.dataset.checkinId;
    if (!id) { toast('Save a Pulse before rating its reflection.', 'info'); return; }
    try { await fetchJSON(`/api/check-ins/${encodeURIComponent(id)}/feedback`, { method: 'POST', body: { relevant: button.dataset.feedback === 'true' } });$$('button', group).forEach(b => b.setAttribute('aria-pressed', String(b === button))); toast('Thank you—feedback saved.'); }
    catch (error) { toast(error.message, 'error'); }
  }));

  // Bridge live preview, explicit editing and approval boundary.
  const bridgeForm = $('[data-bridge-form]');
  const approveBrief = $('[data-approve-brief]'); const bookCta = $('[data-book-cta]'); const revokeBrief = $('[data-revoke-brief]');
  const replacementWarning = $('[data-replacement-warning]'); const replaceApproval = $('#replace_approved'); const createBriefButton = $('[data-create-brief]');
  const approvalLabel = $('label[for="approve_brief"]'); let bridgeDirty = false;
  const bridgeMap = { topic: 'topic', context: 'context', outcome: 'outcome', questions: 'questions' };
  function updateBrief() {
    if (!bridgeForm) return;
    Object.entries(bridgeMap).forEach(([input, output]) => {
      const source = bridgeForm.elements[input]; const target = $(`[data-brief-field="${output}"]`);
      if (source && target && source.value.trim()) target.textContent = source.tagName === 'SELECT' ? source.options[source.selectedIndex].text : source.value;
    });
    const topic = bridgeForm.elements.topic?.value || 'personal_growth';
    const specialties = { career:'Career & purpose',relationship:'Relationships',finance:'Finance reflection',education:'Education & direction',family:'Family dynamics',personal_growth:'Personal growth' };
    $('[data-speciality]').textContent = specialties[topic] || 'Life direction';
    $('[data-speciality-why]').textContent = `Suggested only because you chose ${topic.replace('_',' ')} as the topic.`;
  }
  function markBridgeDirty() {
    if (!bridgeForm?.dataset.briefId) return;
    bridgeDirty=true; approveBrief.checked=false; approveBrief.disabled=true;
    bookCta.setAttribute('aria-disabled','true'); bookCta.classList.add('button-ghost');
    if(approvalLabel)approvalLabel.textContent='Unsaved changes are not approved. Create the updated draft before reviewing approval.';
    const status=$('[data-approval-status]');if(status)status.textContent='The visible edits are local until you create the updated draft.';
  }
  bridgeForm?.addEventListener('input', () => { updateBrief(); markBridgeDirty(); }); updateBrief();
  const checkinShare = $('#include_checkins', bridgeForm || document); const checkinPreview = $('[data-checkin-share-preview]');
  const updateCheckinPreview = () => { if (checkinPreview) checkinPreview.hidden = !checkinShare?.checked; };
  checkinShare?.addEventListener('change', updateCheckinPreview); updateCheckinPreview();
  $('[data-refresh-checkins]')?.addEventListener('click', button => {
    let entries=[];try{entries=JSON.parse(button.currentTarget.dataset.checkins||'[]')}catch(_){entries=[]}
    const rows=$('[data-checkin-share-rows]');if(!rows||!entries.length)return;rows.replaceChildren();
    entries.forEach(entry=>{const hidden=document.createElement('input');hidden.type='hidden';hidden.name='checkin_ids';hidden.value=entry.id;const section=document.createElement('div');section.className='brief-section';const summary=document.createElement('p');const strong=document.createElement('strong');strong.textContent=`${String(entry.emotional_state||'').replace(/^./,c=>c.toUpperCase())} · confidence ${entry.confidence}/5`;summary.append(strong);const concern=document.createElement('p');concern.textContent=entry.concern;section.append(summary,concern);rows.append(hidden,section);});
    checkinShare.checked=true;updateCheckinPreview();markBridgeDirty();toast('Latest Pulse entries loaded for review. Save a new draft before approval.','info');
  });
  $('[data-edit-brief]')?.addEventListener('click', () => {
    bridgeForm?.scrollIntoView({ behavior:motionBehavior, block:'start' });
    bridgeForm?.elements.context?.focus();
    toast('Edit the source fields, then create a new private draft.', 'info');
  });
  approveBrief?.addEventListener('change', async () => {
    if (!approveBrief.checked) return;
    const id = bridgeForm?.dataset.briefId; const status = $('[data-approval-status]');
    if (bridgeDirty) { approveBrief.checked=false; approveBrief.disabled=true; if(status)status.textContent='Save the visible edits as a new draft before approval.'; return; }
    if (!id) { approveBrief.checked = false; approveBrief.disabled = true; if (status) status.textContent = 'Create the draft before approving it.'; return; }
    approveBrief.disabled = true; if (status) status.textContent = 'Recording your approval…';
    try { await fetchJSON(`/api/briefs/${encodeURIComponent(id)}/approve`, { method:'POST', body:{ approved:true } }); bookCta.setAttribute('aria-disabled','false'); bookCta.classList.remove('button-ghost'); approveBrief.disabled=true; if(approvalLabel)approvalLabel.textContent='Approval recorded. Withdraw it below or create a new draft to change what is shared.'; if(replacementWarning)replacementWarning.hidden=false;if(replaceApproval){replaceApproval.disabled=false;replaceApproval.required=true;}if(createBriefButton)createBriefButton.textContent='Create replacement and withdraw current access';if (revokeBrief) revokeBrief.hidden=false; if (status) status.textContent = 'Approved. This brief and its frozen context snapshot may now appear in the sample console.'; toast('Brief approved.'); }
    catch (error) { approveBrief.checked=false; if (status) status.textContent=error.message; }
    finally { if (!approveBrief.checked) approveBrief.disabled=false; }
  });
  revokeBrief?.addEventListener('click', async () => {
    const id = bridgeForm?.dataset.briefId; const status = $('[data-approval-status]'); if (!id) return;
    revokeBrief.disabled=true;
    try { await fetchJSON(`/api/briefs/${encodeURIComponent(id)}/revoke`, {method:'POST',body:{confirm:true}}); approveBrief.checked=false; approveBrief.disabled=true; if(approvalLabel)approvalLabel.textContent='This brief was withdrawn and cannot be re-approved. Create a new draft to share again.';if(checkinShare)checkinShare.checked=false;if(checkinPreview){checkinPreview.hidden=true;const rows=$('[data-checkin-share-rows]');if(rows){rows.replaceChildren();const note=document.createElement('p');note.className='fine-print';note.textContent='The withdrawn snapshot was deleted.';rows.append(note);}} if(replacementWarning)replacementWarning.hidden=true;if(replaceApproval){replaceApproval.checked=false;replaceApproval.disabled=true;replaceApproval.required=false;}if(createBriefButton)createBriefButton.textContent='Create my editable brief';revokeBrief.hidden=true; bookCta.setAttribute('aria-disabled','true'); bookCta.classList.add('button-ghost'); if(status)status.textContent='Console access withdrawn. The frozen Pulse snapshot was deleted; save a new draft to share again.'; toast('Brief access withdrawn.','info'); }
    catch(error){ if(status)status.textContent=error.message; }
    finally { revokeBrief.disabled=false; }
  });
  bookCta?.addEventListener('click', event => { if (bookCta.getAttribute('aria-disabled') === 'true') { event.preventDefault(); toast('Review and approve the brief before booking.', 'info'); } });
  bridgeForm?.addEventListener('submit', async event => {
    event.preventDefault(); if (!bridgeForm.reportValidity()) return;
    const payload = formObject(bridgeForm);
    payload.questions = String(payload.questions).split('\n').map(q => q.trim()).filter(Boolean);
    setBusy(bridgeForm, true, 'Creating your private draft…');
    try { const data = await fetchJSON('/api/briefs', { method: 'POST', body: payload }); bridgeForm.dataset.briefId = data.id || data.brief_id || ''; bridgeDirty=false; const replaced=payload.replace_approved===true; setBusy(bridgeForm, false, replaced?'Replacement draft saved; prior console access was withdrawn. Review and approve the new draft when ready.':'Draft created. Review and approve it when ready.'); approveBrief.disabled=false; approveBrief.checked=false; if(approvalLabel)approvalLabel.textContent='I reviewed and approve this brief for the demo consultation.';if(replacementWarning)replacementWarning.hidden=true;if(replaceApproval){replaceApproval.checked=false;replaceApproval.disabled=true;replaceApproval.required=false;}if(createBriefButton)createBriefButton.textContent='Create my editable brief'; if(revokeBrief)revokeBrief.hidden=true; bookCta.setAttribute('aria-disabled','true'); bookCta.classList.add('button-ghost'); toast(replaced?'Replacement saved; prior access withdrawn.':'Editable brief created.',replaced?'info':'success'); }
    catch (error) { setBusy(bridgeForm, false, error.message); }
  });

  // Sample booking.
  const bookingForm = $('[data-booking-form]');
  $$('input[name="astrologer_id"]', bookingForm || document).forEach(input => input.addEventListener('change', () => {
    $$('.astrologer', bookingForm).forEach(card => card.classList.toggle('selected-card', card.contains(input) && input.checked));
  }));
  $('input[name="astrologer_id"]:checked', bookingForm || document)?.dispatchEvent(new Event('change'));
  bookingForm?.addEventListener('submit', async event => {
    event.preventDefault(); if (!bookingForm.reportValidity()) return; const payload=formObject(bookingForm);setBusy(bookingForm, true, 'Saving sample booking…');
    try { await fetchJSON('/api/bookings', { method:'POST', body:payload }); setBusy(bookingForm, false, 'Sample booking saved. No payment was made.'); $('[data-booking-confirmation]').hidden = false; $('[data-booking-confirmation]').scrollIntoView({ behavior:motionBehavior, block:'center' }); }
    catch (error) { setBusy(bookingForm, false, error.message); }
  });

  // Follow-up continuity.
  const followupForm = $('[data-followup-form]');
  followupForm?.addEventListener('submit', async event => {
    event.preventDefault(); if (!followupForm.reportValidity()) return; const payload = formObject(followupForm);
    payload.actions = (Array.isArray(payload.actions) ? payload.actions : [payload.actions]).filter(Boolean);
    setBusy(followupForm, true, 'Saving your approved follow-up…');
    try { await fetchJSON('/api/follow-up', { method:'POST', body:payload }); setBusy(followupForm, false, 'Follow-up saved to your Journey.'); toast('Your continuity plan is ready.'); }
    catch (error) { setBusy(followupForm, false, error.message); }
  });

  // Circle invitation, secure link sharing, privacy-safe SVG and PNG.
  const circle = $('[data-circle]'); const circleConsent = $('[data-circle-consent]'); let shareUrl = $('[data-share-url]')?.value || '';
  function enableSharing(url, expiry) {
    shareUrl = new URL(url, location.origin).href; const input = $('[data-share-url]'); if (input) input.value = shareUrl;
    const copy = $('[data-copy-link]'); const cardButtons = $$('[data-download-card]'); if (copy) copy.disabled = false; cardButtons.forEach(b => b.disabled = false);
    const whats = $('[data-whatsapp]'); if (whats) { whats.href = `https://wa.me/?text=${encodeURIComponent(`A private AstroLive Orbit Circle invitation: ${shareUrl}`)}`; whats.removeAttribute('aria-disabled'); }
    const expires = $('[data-expiry]'); if (expiry && expires) expires.textContent = `This invitation expires ${new Date(expiry).toLocaleString()}.`;
  }
  function disableSharing() {
    shareUrl=''; const input=$('[data-share-url]'); if(input)input.value='Create an invitation to generate a private link';
    const copy=$('[data-copy-link]'); if(copy)copy.disabled=true; $$('[data-download-card]').forEach(button=>button.disabled=true);
    const whats=$('[data-whatsapp]'); if(whats){whats.href='#';whats.setAttribute('aria-disabled','true');}
  }
  function setCircleProgress(status) {
    const reached=status==='completed'?4:status==='opened'?2:status==='created'?1:0;
    $$('[data-circle-step]').forEach((step,index)=>{const done=index<reached;step.classList.toggle('is-complete',done);const marker=$('span',step),copy=$('p',step);if(marker)marker.textContent=done?'✓':String(index+1);if(copy)copy.textContent=done?'Complete':'Waiting safely';});
  }
  circleConsent?.addEventListener('change', async () => {
    const status=$('[data-circle-status]'); circleConsent.disabled=true;
    try { await fetchJSON('/api/consents/circle',{method:'POST',body:{granted:circleConsent.checked}}); if(!circleConsent.checked){disableSharing();setCircleProgress('none');const insight=$('[data-owner-mutual-insight]');if(insight)insight.hidden=true;if(status)status.textContent='Circle consent withdrawn. Existing links were revoked.';} else if(status)status.textContent='Circle consent enabled. No invitation has been created yet.'; }
    catch(error){circleConsent.checked=!circleConsent.checked;if(status)status.textContent=error.message;}
    finally{circleConsent.disabled=false;}
  });
  if (shareUrl && !shareUrl.startsWith('Create an invitation')) enableSharing(shareUrl, circle?.dataset.referralExpiry);
  $('[data-whatsapp]')?.addEventListener('click',event=>{if(event.currentTarget.getAttribute('aria-disabled')==='true'){event.preventDefault();toast('Create a private invitation first.','info');}});
  $('[data-create-invite]')?.addEventListener('click', async button => {
    button.disabled = true; const status = $('[data-circle-status]'); if (status) status.textContent = 'Creating an expiring private token…';
    try { if (!circleConsent?.checked) throw new Error('Choose the Circle consent box before creating an invitation.'); await fetchJSON('/api/consents/circle',{method:'POST',body:{granted:true}}); const data = await fetchJSON('/api/referrals', { method:'POST', body:{} }); const url = data.url || `${location.origin}/circle/${data.token}`; enableSharing(url, data.expires_at);setCircleProgress('created');const insight=$('[data-owner-mutual-insight]');if(insight)insight.hidden=true;if (status) status.textContent = 'Private invitation created. The URL contains only a random token.'; }
    catch (error) { if (status) status.textContent = error.message; } finally { button.disabled = false; }
  });
  $('[data-copy-link]')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(shareUrl); toast('Private link copied.'); }
    catch (_) { const input = $('[data-share-url]'); input.select(); document.execCommand('copy'); toast('Private link copied.'); }
  });
  function safeCardSVG() {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="700" viewBox="0 0 1200 700"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#252455"/><stop offset=".65" stop-color="#51368b"/><stop offset="1" stop-color="#74504b"/></linearGradient></defs><rect width="1200" height="700" rx="36" fill="url(#g)"/><g fill="none" stroke="#fff" opacity=".16"><ellipse cx="1020" cy="90" rx="300" ry="100" transform="rotate(-20 1020 90)"/><circle cx="80" cy="700" r="290"/></g><circle cx="83" cy="90" r="29" fill="none" stroke="#f0bf68" stroke-width="2"/><circle cx="83" cy="90" r="7" fill="#f0bf68"/><g fill="#fff" font-family="Arial,sans-serif"><text x="130" y="82" font-size="28" font-weight="700">AstroLive</text><text x="130" y="112" font-size="20" fill="#f0bf68" letter-spacing="4">ORBIT CIRCLE</text><text x="72" y="310" font-size="46" font-weight="600">A small pause can make a shared</text><text x="72" y="370" font-size="46" font-weight="600">conversation feel lighter.</text><text x="72" y="610" font-size="23" fill="#ffe2aa">Private invitation · No personal details embedded</text></g></svg>`;
  }
  $$('[data-download-card]').forEach(button => button.addEventListener('click', () => {
    const format = button.dataset.downloadCard || 'png'; const svg = safeCardSVG();
    if (format === 'svg') { download(svg, 'image/svg+xml', 'orbit-circle-safe-card.svg'); return; }
    const image = new Image(); const source = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    image.onload = () => { const canvas = document.createElement('canvas'); canvas.width=1200; canvas.height=700; canvas.getContext('2d').drawImage(image,0,0); canvas.toBlob(blob => { const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url;a.download='orbit-circle-safe-card.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),500); },'image/png'); }; image.src = source;
  }));

  const inviteForm = $('[data-invite-form]');
  inviteForm?.addEventListener('submit', async event => {
    event.preventDefault(); if (!inviteForm.reportValidity()) return; setBusy(inviteForm,true,'Completing your consented check-in…');
    try { const data = await fetchJSON(inviteForm.action, { method:'POST', body:formObject(inviteForm) }); setBusy(inviteForm,false,'Your check-in is complete.'); const insight=$('[data-mutual-insight]'); if (data.mutual_insight) { $('[data-mutual-insight-text]').textContent=data.mutual_insight; insight.hidden=false; insight.scrollIntoView({behavior:motionBehavior});$$('input,select,button',inviteForm).forEach(control=>control.disabled=true); } else toast('This invitation was already completed; no prior participant data was revealed.', 'info'); }
    catch (error) { setBusy(inviteForm,false,error.message); }
  });

  // Journey actions, feedback, and destructive reset confirmation.
  $$('.completion-toggle').forEach(button => { if(button.getAttribute('aria-pressed')==='true') button.disabled=true; button.addEventListener('click', async () => {
    if (button.getAttribute('aria-pressed') === 'true') return;
    try { let data={changed:true};if (!String(button.dataset.actionId).startsWith('demo-')) data=await fetchJSON(button.dataset.actionEndpoint || `/api/journey/actions/${encodeURIComponent(button.dataset.actionId)}/complete`, { method:'POST', body:{} }); button.setAttribute('aria-pressed','true'); button.textContent='Completed'; button.disabled=true;if(data.changed!==false){const count=$('[data-action-count]');const progress=$('[data-action-progress]');if(count){const total=safeNumber(count.dataset.total,0),completed=Math.min(total,safeNumber(count.dataset.completed,0)+1);count.dataset.completed=String(completed);const value=$('[data-completed-actions]',count);if(value)value.textContent=String(completed);if(progress){progress.value=completed;progress.textContent=`${completed} of ${total}`;}}} toast('Action completed.'); }
    catch(error){ toast(error.message,'error'); }
  }); });
  $$('[data-helpfulness-value]').forEach(button => button.addEventListener('click', () => {
    const group = button.closest('.feedback-row');
    $$('[data-helpfulness-value]', group).forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    const input = $('[data-helpfulness-input]', group);
    if (input) input.value = button.dataset.helpfulnessValue;
  }));
  $$('[data-consultation-feedback] button').forEach(button => button.addEventListener('click', async () => { const group=button.closest('[data-consultation-feedback]');try{await fetchJSON('/api/feedback',{method:'POST',body:{type:'consultation',value:button.dataset.value,booking_id:group.dataset.bookingId}});$$('button',group).forEach(b=>b.setAttribute('aria-pressed',String(b===button)));toast('Feedback saved.');}catch(error){toast(error.message,'error');} }));
  const resetDialog = $('[data-reset-dialog]'); $('[data-reset]')?.addEventListener('click',()=>resetDialog.showModal()); $('[data-cancel-reset]')?.addEventListener('click',()=>resetDialog.close());
  $('[data-confirm-reset]')?.addEventListener('click', async button => { button.disabled=true; try{await fetchJSON('/api/reset',{method:'POST',body:{confirm:true}});location.assign('/onboarding');}catch(error){button.disabled=false;toast(error.message,'error');} });

  // Canvas charts: local, responsive and dependency-free.
  const palette = { violet:'#a56cf5', mint:'#73dbba', gold:'#f0bf68', indigo:'#6f6bf5', rose:'#fa8eac', grid:'rgba(225,220,255,.12)', text:'#b4b3ce' };
  function canvasSetup(canvas) { const rect=canvas.getBoundingClientRect(); const dpr=Math.min(devicePixelRatio||1,2); canvas.width=Math.max(300,rect.width*dpr);canvas.height=Math.max(170,rect.height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);return {ctx,w:rect.width,h:rect.height}; }
  function axes(ctx,w,h){ctx.strokeStyle=palette.grid;ctx.lineWidth=1;for(let i=1;i<5;i++){const y=20+(h-50)*i/5;ctx.beginPath();ctx.moveTo(34,y);ctx.lineTo(w-10,y);ctx.stroke();}}
  function lineChart(canvas){const {ctx,w,h}=canvasSetup(canvas);axes(ctx,w,h);const series=[[42,46,43,51,55,54,62,58,67,70,66,74,71,77,82,78,85,89,86,94,98,96,104,108,103,112,116,114,121,126],[31,34,33,39,43,41,47,46,51,53,50,58,55,60,63,61,68,70,69,74,79,76,81,84,82,88,91,89,95,99]];const colors=[palette.violet,palette.mint];series.forEach((data,s)=>{ctx.strokeStyle=colors[s];ctx.lineWidth=2.5;ctx.beginPath();data.forEach((v,i)=>{const x=35+i*(w-52)/(data.length-1),y=h-25-(v/135)*(h-50);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()});}
  function chartValues(canvas){try{return JSON.parse(canvas.dataset.values||'[]').map(Number)}catch(_){return[]}}
  function bars(canvas){const {ctx,w,h}=canvasSetup(canvas);axes(ctx,w,h);const vals=chartValues(canvas),labels=['D1','D7','D30','Pulse','Consult','Repeat'];if(!vals.length)return;const max=Math.max(0.01,...vals)*1.12,bw=(w-55)/vals.length*.58;ctx.font='11px sans-serif';ctx.textAlign='center';labels.forEach((l,i)=>{const x=42+i*(w-55)/vals.length;const barH=(vals[i]||0)/max*(h-60);ctx.fillStyle=i<3?palette.violet:palette.gold;ctx.fillRect(x,h-28-barH,bw,barH);ctx.fillStyle=palette.text;ctx.fillText(l,x+bw/2,h-9)});}
  function donut(canvas){const {ctx,w,h}=canvasSetup(canvas);const vals=chartValues(canvas),total=vals.reduce((a,b)=>a+b,0),colors=[palette.violet,palette.mint,palette.gold,palette.indigo,palette.rose];if(!total)return;let angle=-Math.PI/2;vals.forEach((v,i)=>{const next=angle+Math.PI*2*v/total;ctx.beginPath();ctx.arc(w/2,h/2,Math.min(w,h)*.32,angle,next);ctx.strokeStyle=colors[i%colors.length];ctx.lineWidth=24;ctx.stroke();angle=next});ctx.fillStyle='#fff';ctx.font='700 25px sans-serif';ctx.textAlign='center';ctx.fillText(String(vals.length),w/2,h/2+4);ctx.fillStyle=palette.text;ctx.font='11px sans-serif';ctx.fillText('segments',w/2,h/2+22);}
  function distributionChart(canvas){const {ctx,w,h}=canvasSetup(canvas);const vals=chartValues(canvas),max=Math.max(1,...vals);if(!vals.length)return;const gap=5,bw=(w-20-(vals.length-1)*gap)/vals.length;vals.forEach((v,i)=>{const bh=v/max*(h-25);ctx.fillStyle=canvas.dataset.accent==='gold'?palette.gold:palette.violet;ctx.fillRect(10+i*(bw+gap),h-12-bh,bw,bh)});}
  function scenarioChart(canvas, values){const {ctx,w,h}=canvasSetup(canvas);axes(ctx,w,h);if(!values)return;const summaryId=canvas.getAttribute('aria-describedby'),summary=summaryId?document.getElementById(summaryId):null,rounded=value=>Math.round(value||0).toLocaleString('en-IN');if(summary)summary.textContent=`Median scenario values: baseline retained users ${rounded(values.baseline[0])}; Orbit retained users ${rounded(values.orbit[0])}; baseline consultations ${rounded(values.baseline[1])}; Orbit consultations ${rounded(values.orbit[1])}; baseline organic users ${rounded(values.baseline[2])}; Orbit organic users ${rounded(values.orbit[2])}.`;const max=Math.max(1,...values.baseline,...values.orbit)*1.2;const labels=['Retained','Consults','Organic'];const group=(w-55)/3;labels.forEach((label,i)=>{const x=45+i*group,bw=Math.min(35,group*.25);[[values.baseline[i],palette.indigo],[values.orbit[i],palette.gold]].forEach(([v,c],j)=>{const bh=v/max*(h-62);ctx.fillStyle=c;ctx.fillRect(x+j*(bw+5),h-30-bh,bw,bh)});ctx.fillStyle=palette.text;ctx.font='11px sans-serif';ctx.textAlign='center';ctx.fillText(label,x+bw,h-10)});}
  function drawCharts(){ $$('canvas[data-chart]').forEach(canvas=>{const type=canvas.dataset.chart;if(type==='trend')lineChart(canvas);if(type==='bars')bars(canvas);if(type==='donut')donut(canvas);if(type==='distribution')distributionChart(canvas);if(type==='scenario')scenarioChart(canvas,canvas._scenario);}); }
  let resizeTimer; window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(drawCharts,120)}); drawCharts();

  // Dashboard filter contract and privacy-safe export.
  const dashboard=$('[data-dashboard]');if(dashboard){try{context.analytics=JSON.parse(dashboard.dataset.analytics||'{}')}catch(_){context.analytics={}}}
  $('[data-export-dashboard]')?.addEventListener('click',()=>download(JSON.stringify({exported_at:new Date().toISOString(),labels:'Synthetic demo unless explicitly marked model-derived',filters:formObject($('[data-dashboard-filters]')),metrics:context.analytics||{}},null,2),'application/json','orbit-growth-snapshot.json'));

  // Monte Carlo simulation with server-first execution and functional local fallback.
  const simulatorForm = $('[data-simulator-form]'); let latestSimulation = null; let initialSimulation = null;
  function mulberry32(seed){return function(){let t=seed+=0x6D2B79F5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return((t^t>>>14)>>>0)/4294967296;};}
  function quantile(sorted,q){const i=(sorted.length-1)*q,lo=Math.floor(i),hi=Math.ceil(i);return sorted[lo]+(sorted[hi]-sorted[lo])*(i-lo);}
  function localSimulation(input){const random=mulberry32(2026),trials=Math.max(10000,Math.min(100000,safeNumber(input.trials,10000))),retained=[],consults=[],organic=[],baselineRetained=[],scenarioRetained=[],baselineConsults=[],scenarioConsults=[];for(let i=0;i<trials;i++){const jitter=.82+random()*.36,baseR=input.eligible_users*input.baseline_retention*jitter,incR=input.eligible_users*input.pulse_adoption*input.baseline_retention*input.retention_uplift*jitter,baseC=input.eligible_users*input.baseline_consultation_conversion*jitter,orbitC=input.eligible_users*input.consultation_conversion*(1+input.repeat_consultation_uplift)*jitter;baselineRetained.push(baseR);scenarioRetained.push(baseR+incR);retained.push(incR);baselineConsults.push(baseC);scenarioConsults.push(orbitC);consults.push(orbitC-baseC);organic.push(input.eligible_users*input.pulse_adoption*input.share_rate*input.invites_per_sharer*input.invite_conversion*(.8+random()*.4));}const summary=values=>{values.sort((a,b)=>a-b);return{p05:quantile(values,.05),median:quantile(values,.5),expected:values.reduce((a,b)=>a+b,0)/values.length,p95:quantile(values,.95)}};const metrics={baseline_retained_users:summary(baselineRetained),scenario_retained_users:summary(scenarioRetained),incremental_retained_users:summary(retained),baseline_consultations:summary(baselineConsults),scenario_consultations:summary(scenarioConsults),incremental_consultations:summary(consults),incremental_organic_users:summary(organic)};if(input.average_consultation_revenue>0)metrics.incremental_revenue=summary(consults.map(v=>v*input.average_consultation_revenue));return{inputs:input,metrics,sensitivity:[],revenue_supported:input.average_consultation_revenue>0,label:'Client fallback scenario estimate — not measured impact'};}
  function renderSimulation(result,input){const metrics=result.metrics||{},actualInputs=result.inputs||input||{};latestSimulation={assumptions:actualInputs,results:result,generated_at:new Date().toISOString(),label:'Scenario estimate, not measured impact'};const ret=metrics.incremental_retained_users||{},con=metrics.incremental_consultations||{},org=metrics.incremental_organic_users||{},rev=metrics.incremental_revenue||{};const revenueSupported=result.revenue_supported===true;const values={retained:Math.round(ret.median??0),consultations:Math.round(con.median??0),organic:Math.round(org.median??0),revenue:revenueSupported?`₹${Math.round(rev.median??0).toLocaleString('en-IN')}`:'Unavailable',p5:`P5 · ${Math.round(ret.p05??0)}`,median:`Median · ${Math.round(ret.median??0)}`,p95:`P95 · ${Math.round(ret.p95??0)}`};Object.entries(values).forEach(([k,v])=>{const el=$(`[data-result="${k}"]`);if(el)el.textContent=v});const label=$('[data-trial-label]');if(label)label.textContent=`${safeNumber(actualInputs.trials,10000).toLocaleString()} trials`;const canvas=$('canvas[data-chart="scenario"]');if(canvas){canvas._scenario={baseline:[metrics.baseline_retained_users?.median||0,metrics.baseline_consultations?.median||0,0],orbit:[metrics.scenario_retained_users?.median||0,metrics.scenario_consultations?.median||0,org.median||0]};scenarioChart(canvas,canvas._scenario);}const sensitivity=$('[data-sensitivity]');if(sensitivity){sensitivity.replaceChildren();const rows=result.sensitivity||[];if(!rows.length){const p=document.createElement('p');p.className='muted';p.textContent='Sensitivity is unavailable for this fallback scenario.';sensitivity.append(p);}rows.slice(0,7).forEach(row=>{const wrap=document.createElement('div');wrap.className='sensitivity-row';const name=document.createElement('span');name.textContent=row.factor;const progress=document.createElement('progress');progress.max=1;progress.value=safeNumber(row.absolute_influence,0);const value=document.createElement('b');value.textContent=safeNumber(row.correlation,0).toFixed(3);wrap.append(name,progress,value);sensitivity.append(wrap);});}}
  simulatorForm?.addEventListener('submit',async event=>{event.preventDefault();if(!simulatorForm.reportValidity())return;const input=formObject(simulatorForm);Object.keys(input).forEach(k=>input[k]=safeNumber(input[k],0));setBusy(simulatorForm,true,'Running uncertainty trials…');try{let result;try{result=await fetchJSON('/api/experiments',{method:'POST',body:input});}catch(error){if(error.status&&error.status<500)throw error;result=localSimulation(input);toast('Server unavailable; showing a labeled deterministic local fallback.','info');}renderSimulation(result,input);setBusy(simulatorForm,false,'Scenario complete. Estimates are not measured impact.');}catch(error){setBusy(simulatorForm,false,error.message);}});
  function flatten(value,prefix='',rows=[]){Object.entries(value||{}).forEach(([key,item])=>{const path=prefix?`${prefix}.${key}`:key;if(item&&typeof item==='object'&&!Array.isArray(item))flatten(item,path,rows);else rows.push([path,Array.isArray(item)?JSON.stringify(item):item]);});return rows;}
  $$('[data-download]').forEach(button=>button.addEventListener('click',()=>{if(!latestSimulation){const input=formObject(simulatorForm);Object.keys(input).forEach(k=>input[k]=safeNumber(input[k],0));renderSimulation(localSimulation(input),input);}const runId=latestSimulation.results?.run_id;if(runId){const link=document.createElement('a');link.href=`/api/experiments/${encodeURIComponent(runId)}.${button.dataset.download}`;link.download='';document.body.append(link);link.click();link.remove();return;}if(button.dataset.download==='json')download(JSON.stringify(latestSimulation,null,2),'application/json','orbit-scenario.json');else{const rows=[['section','metric','value'],...flatten(latestSimulation.assumptions).map(([k,v])=>['assumption',k,v]),...flatten(latestSimulation.results).map(([k,v])=>['result',k,v])];download(rows.map(r=>r.map(x=>`"${String(x).replace(/"/g,'""')}"`).join(',')).join('\n'),'text/csv','orbit-scenario.csv');}}));
  const simulator=$('[data-simulator]');if(simulator){try{initialSimulation=JSON.parse(simulator.dataset.initialResult||'{}');if(initialSimulation.metrics)renderSimulation(initialSimulation,initialSimulation.inputs||formObject(simulatorForm));}catch(_){/* Initial estimate is optional. */}}
  simulatorForm?.addEventListener('reset',()=>window.setTimeout(()=>{if(initialSimulation?.metrics)renderSimulation(initialSimulation,formObject(simulatorForm));const status=$('[data-form-status]',simulatorForm);if(status)status.textContent='Assumptions and results reset to the documented baseline.';},0));
})();
