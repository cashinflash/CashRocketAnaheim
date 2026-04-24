/* ═══════════════════════════════════════
   CASH IN FLASH — MAIN JAVASCRIPT
   ═══════════════════════════════════════ */

(function () {
  'use strict';

  /* ---------- STICKY HEADER SHADOW ----------
     IntersectionObserver-based: a 10px sentinel at the top of the
     document toggles `scrolled` on the header when the page scrolls
     past it. Zero scroll-listener work, zero forced reflow. */
  var header = document.getElementById('site-header');
  if (header && 'IntersectionObserver' in window) {
    var sentinel = document.createElement('div');
    sentinel.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:10px;pointer-events:none';
    sentinel.setAttribute('aria-hidden', 'true');
    document.body.prepend(sentinel);
    var hdrObserver = new IntersectionObserver(function (entries) {
      header.classList.toggle('scrolled', !entries[0].isIntersecting);
    }, { threshold: 0 });
    hdrObserver.observe(sentinel);
  } else if (header) {
    // Fallback for ancient browsers
    window.addEventListener('scroll', function () {
      header.classList.toggle('scrolled', window.scrollY > 10);
    }, { passive: true });
  }

  /* ---------- MOBILE MENU ---------- */
  var toggle = document.getElementById('menu-toggle');
  var mobileMenu = document.getElementById('mobile-menu');
  var overlay = document.getElementById('mobile-overlay');

  function openMenu() {
    toggle.classList.add('active');
    mobileMenu.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeMenu() {
    toggle.classList.remove('active');
    mobileMenu.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
  }

  toggle.addEventListener('click', function () {
    mobileMenu.classList.contains('open') ? closeMenu() : openMenu();
  });
  overlay.addEventListener('click', closeMenu);
  document.getElementById('mobile-menu-close').addEventListener('click', closeMenu);

  /* Mobile sub-menu toggles */
  document.querySelectorAll('.mobile-nav-item.has-sub > a').forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      this.parentElement.classList.toggle('open');
    });
  });

  /* ---------- SCROLL ANIMATIONS ---------- */
  var animatedEls = document.querySelectorAll('.animate-on-scroll');
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });

  animatedEls.forEach(function (el) { observer.observe(el); });

  /* ---------- EDUCATION CAROUSEL ---------- */
  var track = document.getElementById('carousel-track');
  var dotsContainer = document.getElementById('carousel-dots');

  if (track && dotsContainer) {
    var slides = track.querySelectorAll('.carousel-slide');
    var totalOriginal = slides.length / 2; // slides are duplicated in HTML
    var currentPage = 0;

    var mqMobile = window.matchMedia('(max-width: 768px)');
    var mqTablet = window.matchMedia('(max-width: 1024px)');

    function getSlidesPerView() {
      if (mqMobile.matches) return 1;
      if (mqTablet.matches) return 2;
      return 3;
    }

    function getTotalPages() {
      return Math.ceil(totalOriginal / getSlidesPerView());
    }

    var cachedTrackWidth = 0;

    function buildDots() {
      dotsContainer.innerHTML = '';
      var pages = getTotalPages();
      for (var i = 0; i < pages; i++) {
        var dot = document.createElement('span');
        dot.className = 'dot' + (i === currentPage ? ' active' : '');
        dot.dataset.page = i;
        dot.addEventListener('click', function () {
          goToPage(parseInt(this.dataset.page));
        });
        dotsContainer.appendChild(dot);
      }
    }

    function goToPage(page) {
      var perView = getSlidesPerView();
      var pages = getTotalPages();
      currentPage = Math.max(0, Math.min(page, pages - 1));
      var slideWidth = cachedTrackWidth / perView;
      track.style.transform = 'translateX(' + -(currentPage * perView * slideWidth) + 'px)';

      dotsContainer.querySelectorAll('.dot').forEach(function (d, i) {
        d.classList.toggle('active', i === currentPage);
      });
    }

    if ('ResizeObserver' in window) {
      new ResizeObserver(function (entries) {
        cachedTrackWidth = entries[0].contentRect.width;
        buildDots();
        goToPage(0);
      }).observe(track.parentElement);
    } else {
      cachedTrackWidth = track.parentElement.offsetWidth;
      window.addEventListener('resize', function () {
        cachedTrackWidth = track.parentElement.offsetWidth;
        buildDots();
        goToPage(0);
      });
    }
    buildDots();

    /* Touch/swipe support */
    var startX = 0;
    var isDragging = false;

    track.addEventListener('touchstart', function (e) {
      startX = e.touches[0].clientX;
      isDragging = true;
    });
    track.addEventListener('touchend', function (e) {
      if (!isDragging) return;
      isDragging = false;
      var diff = startX - e.changedTouches[0].clientX;
      if (Math.abs(diff) > 50) {
        goToPage(currentPage + (diff > 0 ? 1 : -1));
      }
    });
  }

  /* ---------- FAQ ACCORDION (single open) ---------- */
  var faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(function (item) {
    item.addEventListener('toggle', function () {
      if (this.open) {
        faqItems.forEach(function (other) {
          if (other !== item) other.removeAttribute('open');
        });
      }
    });
  });

  // ---------- Payday Loan Calculator ----------
  var calcSlider = document.getElementById('calc-slider');
  if (calcSlider) {
    var AMOUNTS = [100, 125, 150, 175, 200, 225, 255];
    var FEE_RATE = 45 / 255; // 17.647% — $255 loan = $45 fee = $300 total
    var calcAmount = document.getElementById('calc-amount');
    var calcLoan = document.getElementById('calc-loan');
    var calcFee = document.getElementById('calc-fee');
    var calcTotal = document.getElementById('calc-total');
    var calcCta = document.getElementById('calc-cta');

    function updateCalc() {
      var idx = Number(calcSlider.value);
      var amount = AMOUNTS[idx];
      var fee = Math.round(amount * FEE_RATE * 100) / 100;
      var total = amount + fee;
      var fill = (idx / (AMOUNTS.length - 1)) * 100;

      calcAmount.textContent = '$' + amount;
      calcLoan.textContent = '$' + amount.toFixed(2);
      calcFee.textContent = '$' + fee.toFixed(2);
      calcTotal.textContent = '$' + total.toFixed(2);
      calcCta.textContent = 'Apply for $' + amount;
      calcSlider.style.setProperty('--fill', fill + '%');
    }

    calcSlider.addEventListener('input', updateCalc);
    updateCalc(); // Initialize on load
  }

})();
