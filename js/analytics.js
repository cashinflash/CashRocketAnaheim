/**
 * Cash in Flash — GA4 Conversion Event Tracking
 *
 * Wires up custom events on top of the gtag base snippet already in <head>.
 * All events fire into the same [[GA4_ID]] property.
 *
 * Events emitted:
 *   - apply_click     : User clicks any "Apply Now" button or apply.cashrocketanaheim.com link
 *   - phone_click     : User taps a tel: link
 *   - form_submit     : Contact form (or any <form>) submitted
 *   - location_view   : Page-load on a /locations/* page (with city param)
 *   - money_tip_view  : Page-load on a /money-tips/* article
 *   - outbound_click  : Click on an external link (non-cashrocketanaheim.com domain)
 */
(function () {
  'use strict';

  // Bail if gtag missing (e.g. loaded via cached page before snippet)
  if (typeof window.gtag !== 'function') {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
  }

  var APPLY_VALUE = 25;      // estimated value of a lead click in USD
  var FORM_VALUE = 40;       // estimated value of a form submit

  function slugToCity(slug) {
    return slug.split('-').map(function (w) {
      return w.charAt(0).toUpperCase() + w.slice(1);
    }).join(' ');
  }

  // ─── Auto page-context events on load ────────────────────────────────
  var path = window.location.pathname;

  if (path.indexOf('/locations/') === 0 && path !== '/locations/' && path !== '/locations/index.html') {
    var locSlug = path.replace('/locations/', '').replace('.html', '').replace(/\/$/, '');
    if (locSlug) {
      gtag('event', 'location_view', {
        event_category: 'location',
        event_label: slugToCity(locSlug),
        city: slugToCity(locSlug),
        city_slug: locSlug
      });
    }
  }

  if (path.indexOf('/money-tips/') === 0 && path !== '/money-tips/' && path !== '/money-tips/index.html') {
    var articleSlug = path.replace('/money-tips/', '').replace('.html', '').replace(/\/$/, '');
    if (articleSlug) {
      gtag('event', 'money_tip_view', {
        event_category: 'content',
        event_label: articleSlug,
        article_slug: articleSlug
      });
    }
  }

  // ─── Delegated click listener ────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a');
    if (!a) return;

    var href = a.getAttribute('href') || '';
    var cls = a.className || '';

    // Phone click
    if (href.indexOf('tel:') === 0) {
      gtag('event', 'phone_click', {
        event_category: 'engagement',
        event_label: href.replace('tel:', ''),
        phone_number: href.replace('tel:', '')
      });
      return;
    }

    // Apply Now click — covers .btn-apply, .btn-apply-lg, and any link to apply.cashrocketanaheim.com
    var isApplyBtn = /\bbtn-apply\b/.test(cls);
    var isApplyLink = href.indexOf('apply.cashrocketanaheim.com') !== -1;
    if (isApplyBtn || isApplyLink) {
      gtag('event', 'apply_click', {
        event_category: 'conversion',
        event_label: a.textContent.trim().substring(0, 80) || 'Apply Now',
        value: APPLY_VALUE,
        currency: 'USD',
        link_url: href,
        page_path: path
      });
      return;
    }

    // Login click — separate from apply
    if (/\bbtn-login\b/.test(cls) || href.indexOf('vergentlms.com') !== -1) {
      gtag('event', 'login_click', {
        event_category: 'engagement',
        event_label: 'Customer Login',
        link_url: href
      });
      return;
    }

    // Outbound link tracking (any external non-cashrocketanaheim domain)
    if (/^https?:\/\//i.test(href)) {
      try {
        var u = new URL(href);
        if (u.hostname.indexOf('cashrocketanaheim.com') === -1) {
          gtag('event', 'outbound_click', {
            event_category: 'outbound',
            event_label: u.hostname + u.pathname,
            link_domain: u.hostname,
            link_url: href
          });
        }
      } catch (err) { /* ignore malformed URLs */ }
    }
  }, { passive: true });

  // ─── Form submit listener ────────────────────────────────────────────
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.tagName !== 'FORM') return;

    var formName = form.className || form.id || form.getAttribute('name') || 'form';
    var isContact = /contact/i.test(formName) || /formsubmit\.co/.test(form.action || '');
    var isNewsletter = /newsletter|subscribe/i.test(formName);

    gtag('event', 'form_submit', {
      event_category: 'conversion',
      event_label: isContact ? 'Contact Form' : (isNewsletter ? 'Newsletter' : formName),
      form_type: isContact ? 'contact' : (isNewsletter ? 'newsletter' : 'other'),
      value: isContact ? FORM_VALUE : 0,
      currency: 'USD',
      page_path: path
    });
  }, { passive: true });

  // ─── Optional: scroll-depth milestones (25/50/75/100%) ───────────────
  // Enhanced measurement already fires scroll at 90%, but explicit milestones
  // give richer funnel data.
  var scrollMilestones = [25, 50, 75];
  var firedScroll = {};
  window.addEventListener('scroll', function () {
    var doc = document.documentElement;
    var pct = Math.round(((window.scrollY + window.innerHeight) / doc.scrollHeight) * 100);
    scrollMilestones.forEach(function (m) {
      if (pct >= m && !firedScroll[m]) {
        firedScroll[m] = true;
        gtag('event', 'scroll_depth', {
          event_category: 'engagement',
          event_label: m + '%',
          percent_scrolled: m
        });
      }
    });
  }, { passive: true });
})();
