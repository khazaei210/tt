// Starts the vendored jalalidatepicker (static/vendor/jalalidatepicker.min.js)
// for admin date inputs rendered by AdminJalaliDateWidget (apps/core/admin.py).
// The Django admin doesn't load templates/base.html, which is what wires this
// up for the rest of the site — this is the admin-side equivalent.
document.addEventListener('DOMContentLoaded', () => {
    jalaliDatepicker.startWatch({
        autoHide: true,
        showTodayBtn: true,
        showEmptyBtn: true,
    });
});
