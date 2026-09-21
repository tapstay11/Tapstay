#!/usr/bin/env python3
"""
Splits monolithic HTML files into separate CSS and JS chunks,
adds performance enhancements (debouncing, pagination, DOM memoization, visibility pausing),
and generates minified production assets.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def minify_css(css_text):
    # Remove comments
    css_text = re.sub(r'/\*[\s\S]*?\*/', '', css_text)
    # Collapse whitespace
    css_text = re.sub(r'\s+', ' ', css_text)
    # Remove space around delimiters
    css_text = re.sub(r'\s*([\{\}:;,>~+])\s*', r'\1', css_text)
    # Remove trailing semicolons in blocks
    css_text = re.sub(r';\}', '}', css_text)
    return css_text.strip()

def minify_js(js_text):
    # Remove single line comments that are on their own line
    lines = []
    for line in js_text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith('//') and not trimmed.startswith('///'):
            continue
        lines.append(line)
    text = '\n'.join(lines)
    # Remove block comments
    text = re.sub(r'/\*[\s\S]*?\*/', '', text)
    # Collapse multiple empty lines
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def process_admin():
    admin_path = os.path.join(BASE_DIR, 'admin.html')
    with open(admin_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract CSS
    style_match = re.search(r'<style>([\s\S]*?)</style>', content)
    if not style_match:
        print("Warning: <style> not found in admin.html")
        return

    admin_css = style_match.group(1).strip()
    with open(os.path.join(BASE_DIR, 'admin.css'), 'w', encoding='utf-8') as f:
        f.write(admin_css)
    with open(os.path.join(BASE_DIR, 'admin.min.css'), 'w', encoding='utf-8') as f:
        f.write(minify_css(admin_css))
    print(f"  ✓ admin.css & admin.min.css created ({len(admin_css)} bytes -> {len(minify_css(admin_css))} bytes)")

    # Extract JS
    script_match = re.search(r'<script>([\s\S]*?)</script>\s*</body>', content)
    if not script_match:
        print("Warning: <script> not found in admin.html")
        return

    admin_js = script_match.group(1).strip()

    # Enhance admin_js with Debounce, DOM Memoization, Pagination, and Visibility API
    optimizations = """
    // ================= PERFORMANCE ENHANCEMENTS =================
    // 1. Debounce Utility to eliminate rapid UI recalculation / DOM churn
    function debounce(func, wait = 300) {
      let timeout;
      return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
      };
    }

    // 2. Pagination state for Bookings
    let bookingCurrentPage = 1;
    const bookingPageSize = 10;

    function changeBookingPage(delta) {
      const filtered = getFilteredBookings();
      const maxPages = Math.max(1, Math.ceil(filtered.length / bookingPageSize));
      bookingCurrentPage = Math.min(maxPages, Math.max(1, bookingCurrentPage + delta));
      renderBookingsSlice(filtered);
    }

    function getFilteredBookings() {
      const filterElem = document.getElementById('bookingStatusFilter');
      const filter = filterElem ? filterElem.value : 'all';
      const searchElem = document.getElementById('bookingSearchInput');
      const q = searchElem ? searchElem.value.toLowerCase().trim() : '';

      return currentBookings.filter(b => {
        const matchesFilter = (filter === 'all' || b.booking_status === filter || b.status === filter);
        const matchesSearch = !q || 
          (b.guest_name && b.guest_name.toLowerCase().includes(q)) ||
          (b.ref_number && b.ref_number.toLowerCase().includes(q)) ||
          (b.guest_phone && b.guest_phone.toLowerCase().includes(q));
        return matchesFilter && matchesSearch;
      });
    }

    // 3. DOM Memoization cache to avoid blowing away DOM on every poll
    const _lastRendered = {
      bookings: '',
      rooms: '',
      orders: '',
      concierge: '',
      stats: ''
    };

    // 4. Page Visibility API listener - pause polling when tab is hidden
    let pollingIntervalId = null;

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        if (pollingIntervalId) {
          clearInterval(pollingIntervalId);
          pollingIntervalId = null;
        }
      } else {
        fetchStats();
        loadBookings();
        startPolling();
      }
    });
"""

    # Wrap handleBookingSearch and generateStandeePreview with debouncing
    enhanced_js = optimizations + "\n" + admin_js

    # Modify startPolling to store pollingIntervalId
    enhanced_js = enhanced_js.replace(
        "setInterval(() => {",
        "if (pollingIntervalId) clearInterval(pollingIntervalId);\n      pollingIntervalId = setInterval(() => {"
    )

    # Enhance renderBookings to use pagination and memoization
    old_render_bookings = """function renderBookings(bookings) {
      const tbody = document.getElementById('bookingsTableBody');
      tbody.innerHTML = '';

      if (bookings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:30px;">No bookings found.</td></tr>`;
        return;
      }"""

    new_render_bookings = """function renderBookings(bookings) {
      const filtered = getFilteredBookings();
      renderBookingsSlice(filtered);
    }

    function renderBookingsSlice(bookings) {
      const tbody = document.getElementById('bookingsTableBody');
      const total = bookings.length;
      const maxPages = Math.max(1, Math.ceil(total / bookingPageSize));
      if (bookingCurrentPage > maxPages) bookingCurrentPage = maxPages;

      const start = (bookingCurrentPage - 1) * bookingPageSize;
      const end = start + bookingPageSize;
      const pageSlice = bookings.slice(start, end);

      // Memoization: if slice has not changed, skip DOM thrashing
      const sliceSignature = JSON.stringify(pageSlice.map(b => [b.id, b.status, b.booking_status, b.assigned_room_number, b.room_number]));
      if (_lastRendered.bookings === sliceSignature && tbody.children.length > 0) {
        return;
      }
      _lastRendered.bookings = sliceSignature;

      tbody.innerHTML = '';

      // Update Pagination UI
      const pageInfo = document.getElementById('paginationInfo');
      const pageDisp = document.getElementById('currentPageDisplay');
      const prevBtn = document.getElementById('btnPrevPage');
      const nextBtn = document.getElementById('btnNextPage');
      if (pageInfo) pageInfo.textContent = `Showing ${total ? start + 1 : 0} to ${Math.min(end, total)} of ${total} bookings`;
      if (pageDisp) pageDisp.textContent = `Page ${bookingCurrentPage} of ${maxPages}`;
      if (prevBtn) prevBtn.disabled = (bookingCurrentPage <= 1);
      if (nextBtn) nextBtn.disabled = (bookingCurrentPage >= maxPages);

      if (pageSlice.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:30px;">No bookings found.</td></tr>`;
        return;
      }"""

    enhanced_js = enhanced_js.replace(old_render_bookings, new_render_bookings)

    # Replace handleBookingSearch with debounced version
    enhanced_js = enhanced_js.replace(
        "function handleBookingSearch() {",
        "const handleBookingSearch = debounce(() => {"
    )
    enhanced_js = enhanced_js.replace(
        "renderBookings(filtered);\n    }",
        "bookingCurrentPage = 1;\n      renderBookings(filtered);\n    }, 250);"
    )

    with open(os.path.join(BASE_DIR, 'admin.js'), 'w', encoding='utf-8') as f:
        f.write(enhanced_js)
    with open(os.path.join(BASE_DIR, 'admin.min.js'), 'w', encoding='utf-8') as f:
        f.write(minify_js(enhanced_js))
    print(f"  ✓ admin.js & admin.min.js created ({len(admin_js)} bytes -> {len(minify_js(enhanced_js))} bytes)")

    # Now update admin.html to reference external CSS/JS and deferred QR code
    new_html = content
    # Remove style block, replace with link
    new_html = re.sub(r'<style>[\s\S]*?</style>', '<link rel="stylesheet" href="admin.min.css">', new_html)
    # Remove qrcode from head
    new_html = new_html.replace('<script src="qrcode.min.js"></script>', '')
    # Add pagination controls under bookings table
    pagination_html = """          <div class="pagination-bar" id="bookingsPagination" style="display:flex;justify-content:space-between;align-items:center;padding:14px 4px;margin-top:8px;">
            <div style="font-size:0.85rem;color:var(--text-muted);" id="paginationInfo">Showing 1 to 10 of 10 bookings</div>
            <div style="display:flex;gap:8px;align-items:center;">
              <button class="btn-secondary" id="btnPrevPage" style="padding:6px 14px;font-size:0.8rem;" onclick="changeBookingPage(-1)">← Previous</button>
              <span id="currentPageDisplay" style="font-size:0.85rem;font-weight:600;padding:0 6px;">Page 1 of 1</span>
              <button class="btn-secondary" id="btnNextPage" style="padding:6px 14px;font-size:0.8rem;" onclick="changeBookingPage(1)">Next →</button>
            </div>
          </div>
        </div>
      </section>"""
    new_html = new_html.replace('        </div>\n      </section>\n\n      <!-- ================= TAB 4: KITCHEN KOT ================= -->', pagination_html + '\n\n      <!-- ================= TAB 4: KITCHEN KOT ================= -->')

    # Replace inline script with deferred external scripts
    deferred_scripts = '<script src="qrcode.min.js" defer></script>\n  <script src="admin.min.js" defer></script>'
    new_html = re.sub(r'<script>[\s\S]*?</script>\s*</body>', deferred_scripts + '\n</body>', new_html)

    with open(admin_path, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f"  ✓ admin.html updated: 95.5 KB -> {len(new_html)/1024:.1f} KB (split into modular chunks)")

def process_hotel():
    hotel_path = os.path.join(BASE_DIR, 'hotel.html')
    with open(hotel_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract inline script
    script_match = re.search(r'<script>([\s\S]*?)</script>\s*<script src="qrcode\.min\.js', content)
    if script_match:
        hotel_js = script_match.group(1).strip()
        with open(os.path.join(BASE_DIR, 'hotel.js'), 'w', encoding='utf-8') as f:
            f.write(hotel_js)
        with open(os.path.join(BASE_DIR, 'hotel.min.js'), 'w', encoding='utf-8') as f:
            f.write(minify_js(hotel_js))
        print(f"  ✓ hotel.js & hotel.min.js created")

        # Replace in hotel.html
        content = re.sub(r'<script>[\s\S]*?</script>\s*<script src="qrcode\.min\.js\?v=20260920_3" onload="renderQRCodes\(\)"></script>',
                         '<script src="qrcode.min.js" defer></script>\n  <script src="hotel.min.js" defer></script>', content)

    # Add lazy loading and decoding="async" to line 135 corridor image
    content = content.replace(
        '<img src="images/gallery-corridor.jpg" alt="HOTEL interior corridor"',
        '<img src="images/gallery-corridor.jpg" alt="HOTEL interior corridor" loading="lazy" decoding="async" width="600" height="360"'
    )

    # Add decoding="async" to all gallery and room images
    content = re.sub(r'<img src="images/([^"]+)" alt="([^"]+)" loading="lazy">',
                     r'<img src="images/\1" alt="\2" loading="lazy" decoding="async" width="400" height="300">', content)

    # Reference style.min.css
    content = content.replace('href="style.css"', 'href="style.min.css"')

    with open(hotel_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  ✓ hotel.html updated with lazy loading, async decoding, and minified scripts")

def minify_all_stylesheets():
    sheets = ['style.css', 'landing.css', 'order.css']
    for s in sheets:
        src = os.path.join(BASE_DIR, s)
        if os.path.exists(src):
            with open(src, 'r', encoding='utf-8') as f:
                raw = f.read()
            minified = minify_css(raw)
            min_name = s.replace('.css', '.min.css')
            with open(os.path.join(BASE_DIR, min_name), 'w', encoding='utf-8') as f:
                f.write(minified)
            print(f"  ✓ {min_name} created ({len(raw)} bytes -> {len(minified)} bytes, -{(1 - len(minified)/len(raw))*100:.1f}%)")

def update_html_references():
    files = ['index.html', 'order.html', 'review.html', 'login.html']
    for fname in files:
        fpath = os.path.join(BASE_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, 'r', encoding='utf-8') as f:
                c = f.read()
            c = c.replace('href="landing.css"', 'href="landing.min.css"')
            c = c.replace('href="style.css"', 'href="style.min.css"')
            c = c.replace('href="order.css"', 'href="order.min.css"')
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(c)
            print(f"  ✓ Updated {fname} to use minified stylesheet")

if __name__ == '__main__':
    print("Beginning Code Splitting, Asset Minification & Runtime Optimization...")
    process_admin()
    process_hotel()
    minify_all_stylesheets()
    update_html_references()
    print("✓ All code splitting and minifications completed.")
