// Pure policy shared by all GNOME layouts. The helper repeats these checks
// against fresh server data immediately before a new mutation.
export function resetAvailability(profile, state, now, maxAge = 300) {
    const unavailable = reason => ({enabled: false, reason});
    if (profile?.provider !== 'codex')
        return unavailable('reset.noData');
    if (state?.resetBusy || state?.resetConfirming || state?.refreshing || state?.queued)
        return unavailable('reset.busy');
    if (state?.resetUnsupported)
        return unavailable('reset.unsupported');
    const data = state?.data;
    if (data?.resetStateError)
        return unavailable('reset.stateError');
    if (!data?.ok || state?.error || !data.resetAccount ||
        !Number.isFinite(data.fetchedAt) || now < data.fetchedAt || now - data.fetchedAt > maxAge)
        return unavailable('reset.noData');
    const pending = state.resetAttempt ?? data.resetAttempt;
    if (pending) {
        return pending.account === data.resetAccount
            ? {enabled: true, reason: 'reset.retry', pending}
            : unavailable('reset.accountChanged');
    }
    const rates = data.rateLimits;
    const count = rates?.rateLimitResetCredits?.availableCount;
    if (!Number.isInteger(count) || count < 0)
        return unavailable('reset.noData');
    if (count === 0)
        return unavailable('reset.noCredit');
    const legacy = rates?.rateLimits;
    const bucket = rates?.rateLimitsByLimitId?.codex ??
        (legacy && (!legacy.limitId || legacy.limitId === 'codex') ? legacy : null);
    const windows = [bucket?.primary, bucket?.secondary].filter(window =>
        window && [300, 10080].includes(window.windowDurationMins) &&
        Number.isFinite(window.usedPercent) && window.usedPercent >= 0 && window.usedPercent <= 100 &&
        Number.isFinite(window.resetsAt) && window.resetsAt > now);
    if (!windows.length)
        return unavailable('reset.noData');
    if (!windows.some(window => window.usedPercent >= 90))
        return unavailable('reset.aboveThreshold');
    return {enabled: true, reason: 'reset.ready', count};
}

export function resetResultMessage(payload) {
    if (!payload?.ok) {
        return ({
            reset_unsupported: 'reset.unsupported',
            reset_account_changed: 'reset.accountChanged',
            reset_no_credit: 'reset.noCredit',
            reset_above_threshold: 'reset.aboveThreshold',
            reset_no_data: 'reset.noData',
            reset_state_invalid: 'reset.stateError',
            reset_busy: 'reset.busy',
        })[payload?.errorCode] ?? 'reset.uncertain';
    }
    if (['reset', 'alreadyRedeemed'].includes(payload.outcome))
        return payload.refreshError ? 'reset.successRefreshFailed' : 'reset.success';
    return payload.outcome === 'noCredit' ? 'reset.noCredit' : 'reset.nothingToReset';
}
