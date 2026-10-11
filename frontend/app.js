(() => {
  const $ = (id) => document.getElementById(id);
  const state = { drug: null, quotes: [], sources: {}, total: 0, sort: "total", show: "all", hideOOS: false,
                  currency: "INR", es: null, map: null, layer: null, markers: {}, user: null, basket: [], register: false, basketRequest: 0, addresses: [], addressEdit: null, addressRequest: 0 };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => new Intl.NumberFormat(undefined, { style: "currency", currency: state.currency, maximumFractionDigits: 2 }).format(n);
  const ago = (t) => { const m = Math.max(0, Math.round((Date.now() / 1000 - t) / 60));
    return m < 2 ? "just now" : m < 90 ? `${m} min ago` : m < 2880 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} days ago`; };
  const eta = (m) => m == null ? "" : m < 120 ? `~${m} min` : m < 2880 ? `~${Math.round(m / 60)} h` : `~${Math.round(m / 1440)} days`;
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const say = (t) => { $("msg").textContent = t || ""; };

  async function api(path, method = "GET", body) {
    let response;
    try {
      response = await fetch(path, { method, headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined });
    } catch {
      throw new Error("Could not reach the API server. Check your connection and backend deployment.");
    }
    const contentType = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
    if (contentType !== "application/json" && !contentType.endsWith("+json")) {
      throw new Error("The API returned a web page instead of JSON. The Python backend is missing, unavailable, or the /api route is misconfigured. Netlify static hosting alone cannot run medicine search, login or basket features.");
    }
    let data;
    try { data = await response.json(); }
    catch { throw new Error("The API returned invalid JSON. Check the backend response and deployment logs."); }
    if (!response.ok) {
      if (response.status === 401 && !path.endsWith("/login")) { state.user = null; updateAccount(); }
      throw new Error(typeof data.detail === "string" ? data.detail : "Please check your input and try again.");
    }
    return data;
  }
  const safeLink = (url) => { try { const u = new URL(url); return ["https:", "http:"].includes(u.protocol) ? esc(u.href) : ""; } catch { return ""; } };
  const links = (items) => (items || []).map((item) => safeLink(item.url)
    ? `<a href="${safeLink(item.url)}" target="_blank" rel="noopener noreferrer">Search ${esc(item.provider)}</a>` : "").join("");
  const unitLabel = (drug) => drug.unit === "bottle" ? "bottles" : `${drug.unit || "tablet"}s`;
  const packLabel = (drug) => drug.unit === "bottle" ? `${drug.pack_volume_ml} ml bottle` : `Pack of ${drug.pack_size} ${unitLabel(drug)}`;

  function updateAccount() {
    $("account-link").textContent = state.user ? "Account" : "Log in";
    $("logout").hidden = !state.user;
    $("account-status").textContent = state.user ? `Signed in as ${state.user.email}` : "Browse freely. Log in to save history and a basket.";
    if (!state.user) {
      state.basket = []; state.addresses = []; state.addressRequest++; resetAddressForm();
      $("addresses-list").innerHTML = ""; $("address-editor").hidden = true;
      $("checkout-address").value = ""; renderAddressOptions();
      ["lat", "lng", "pin"].forEach((id) => { $(`basket-${id}`).value = ""; });
      invalidateBasketOffers();
    }
    $("basket-count").textContent = state.basket.length;
  }

  async function route() {
    const page = ["compare", "login", "history", "basket", "addresses"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "compare";
    document.querySelectorAll("[data-page]").forEach((el) => { el.hidden = el.dataset.page !== page; });
    document.querySelectorAll(".navigation a").forEach((el) => {
      if (el.hash === `#${page}`) el.setAttribute("aria-current", "page"); else el.removeAttribute("aria-current");
    });
    if (page === "history") await loadHistory();
    if (page === "basket") await loadBasket();
    if (page === "addresses") await loadAddresses();
    if (page === "login" && state.user) $("auth-message").textContent = `You are signed in as ${state.user.email}. Use Log out to switch accounts.`;
    if (page === "compare" && state.map) setTimeout(() => state.map.invalidateSize(), 50);
  }
  window.addEventListener("hashchange", route);

  $("auth-toggle").addEventListener("click", () => {
    state.register = !state.register;
    $("auth-title").textContent = state.register ? "Create your account" : "Welcome back";
    $("auth-submit").textContent = state.register ? "Create account" : "Log in";
    $("auth-toggle").textContent = state.register ? "Already registered? Log in" : "New here? Create an account";
    $("password").autocomplete = state.register ? "new-password" : "current-password";
    $("auth-message").textContent = "";
  });
  $("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault(); $("auth-submit").disabled = true; $("auth-message").textContent = "";
    try {
      state.user = await api(`/api/auth/${state.register ? "register" : "login"}`, "POST", { email: $("email").value, password: $("password").value });
      $("password").value = ""; updateAccount(); await loadBasket(); location.hash = "compare";
    } catch (error) { $("auth-message").textContent = error.message; }
    finally { $("auth-submit").disabled = false; }
  });
  $("logout").addEventListener("click", async () => {
    try { await api("/api/auth/logout", "POST"); state.user = null; updateAccount(); $("auth-message").textContent = ""; await route(); }
    catch (error) { $("account-status").textContent = error.message; }
  });

  async function selectDrug(id) {
    try {
      const drug = await api(`/api/drugs/${encodeURIComponent(id)}`);
      if (state.es) { state.es.close(); state.es = null; }
      state.quotes = []; state.sources = {};
      ["toolbar", "map", "legend", "summary", "alt"].forEach((key) => { $(key).hidden = true; });
      $("list").innerHTML = ""; $("sources").innerHTML = "";
      if (state.drug?.unit !== drug.unit) $("qty").value = drug.unit === "bottle" ? 1 : 30;
      state.drug = drug; $("q").value = drug.name; suggest.hidden = true;
      document.querySelector('label[for="qty"]').textContent = `Shopping quantity (${unitLabel(drug)})`;
      $("picked").textContent = `Selected: ${drug.name} (${packLabel(drug)})`; $("picked").hidden = false;
      renderMedicine(); refreshGo();
    } catch (error) { say(error.message); }
  }
  function renderMedicine() {
    const d = state.drug, info = d.medicine_info;
    $("welcome").hidden = true; $("medicine-details").hidden = false;
    $("medicine-details").innerHTML = `<h2>${esc(d.name)}</h2><p class="hint">${esc(d.ingredient)} · ${esc(d.form)} · ${esc(packLabel(d))}${d.rx_required ? " · Prescription required" : ""}</p>
      <p class="safety medicine-disclaimer"><strong>Medicine safety disclaimer</strong><br>${esc(info.safety_disclaimer)}</p>
      <p>${esc(info.description)}</p><div class="info-grid"><div><h3>What it is used for</h3><p>${esc(info.uses)}</p><h3>How to use it</h3><p>${esc(info.usage)}</p></div>
      <div><h3>Possible side effects</h3><ul>${(info.side_effects || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div></div>
      <p class="safety">${esc(info.warnings)}</p><p class="hint">${esc(info.notice)}</p>
      <div class="online-links">${safeLink(info.reference) ? `<a href="${safeLink(info.reference)}" target="_blank" rel="noopener noreferrer">Patient information reference</a>` : ""}${links(d.online_searches)}</div>
      <p class="hint">These are pharmacy search links, not verified product listings or stock confirmations. Real connected sources may supply a direct product link below.</p>
      <button id="add-basket" class="primary" type="button">Save medicine to basket</button><p id="medicine-message" role="status"></p>`;
    $("add-basket").addEventListener("click", async () => {
      if (!state.user) { location.hash = "login"; return; }
      try { await api("/api/basket", "PUT", { drug_id: d.id, qty: Number($("qty").value) }); await loadBasket(); $("medicine-message").textContent = "Saved to your basket."; }
      catch (error) { $("medicine-message").textContent = error.message; }
    });
  }

  async function loadHistory() {
    $("history-list").innerHTML = ""; $("clear-history").hidden = true;
    $("history-message").textContent = state.user ? "Loading…" : "Log in to view your private search history.";
    if (!state.user) return;
    try {
      const items = await api("/api/history");
      $("history-message").textContent = items.length ? "" : "No comparisons saved yet. Search for a medicine and compare prices to get started.";
      $("clear-history").hidden = !items.length;
      $("history-list").innerHTML = items.map((item) => `<li class="item saved-item"><h3>${esc(item.drug?.name || item.drug_id)}</h3>
        <p>${item.qty} units · ${esc(new Date(item.created_at * 1000).toLocaleString())}</p><div class="acts"><button data-revisit="${esc(item.drug_id)}" data-qty="${item.qty}">View medicine / compare again</button></div></li>`).join("");
    } catch (error) { $("history-message").textContent = error.message; }
  }
  $("clear-history").addEventListener("click", async () => {
    try { await api("/api/history", "DELETE"); await loadHistory(); } catch (error) { $("history-message").textContent = error.message; }
  });
  async function loadBasket() {
    invalidateBasketOffers();
    $("basket-list").innerHTML = "";
    $("basket-message").textContent = state.user ? "Loading…" : "Log in to save and view your basket.";
    if (!state.user) return;
    try {
      if (!await loadAddresses()) return;
      state.basket = await api("/api/basket"); updateAccount();
      $("basket-message").textContent = state.basket.length ? "" : "Your basket is empty. Select a medicine and save it here.";
      $("basket-list").innerHTML = state.basket.map((item) => `<li class="item saved-item"><h3>${esc(item.drug.name)}</h3>
        <p class="hint">${esc(packLabel(item.drug))}${item.drug.rx_required ? " · Prescription required—use only as prescribed" : ""}</p>
        <div class="basket-quantity"><label for="basket-${esc(item.drug_id)}">Shopping quantity (${esc(unitLabel(item.drug))})</label>
        <input id="basket-${esc(item.drug_id)}" type="number" min="1" max="1000" value="${item.qty}"><button data-update="${esc(item.drug_id)}">Update</button></div>
        <div class="online-links">${links(item.online_searches)}</div><div class="acts"><button data-revisit="${esc(item.drug_id)}" data-qty="${item.qty}">View medicine / compare prices</button><button data-remove="${esc(item.drug_id)}">Remove</button></div></li>`).join("");
      if (!$("checkout-address").value && !$("basket-lat").value && $("lat").value && $("lng").value) {
        ["lat", "lng", "pin"].forEach((id) => { $(`basket-${id}`).value = $(id).value; });
      }
      checkBasket();
    } catch (error) { $("basket-message").textContent = error.message; }
  }

  function invalidateBasketOffers() {
    state.basketRequest++;
    $("basket-offers").innerHTML = "";
    $("basket-check").disabled = false;
    $("basket-compare-message").textContent = "Enter your location to check availability and total costs for the whole basket.";
  }
  async function checkBasket() {
    const requestId = ++state.basketRequest;
    $("basket-check").disabled = false;
    $("basket-offers").innerHTML = "";
    if (!state.user || !state.basket.length) {
      $("basket-compare-message").textContent = state.user ? "Add medicines to compare your whole basket." : "Log in to compare your basket.";
      return;
    }
    if (!$("basket-compare-form").checkValidity()) {
      $("basket-compare-message").textContent = "Enter a valid location to check your basket."; return;
    }
    const p = new URLSearchParams();
    if ($("checkout-address").value) p.set("address_id", $("checkout-address").value);
    if (!$("basket-lat").disabled && ($("basket-lat").value || $("basket-lng").value)) {
      if (!$("basket-lat").value || !$("basket-lng").value) { $("basket-compare-message").textContent = "Enter both coordinates or leave both blank for the selected address."; return; }
      p.set("lat", $("basket-lat").value); p.set("lng", $("basket-lng").value);
    }
    if (!$("checkout-address").value && $("basket-pin").value.trim()) p.set("pincode", $("basket-pin").value.trim());
    $("basket-check").disabled = true;
    $("basket-compare-message").textContent = "Checking every basket item across sources…";
    try {
      const data = await api(`/api/basket/compare?${p}`);
      if (requestId !== state.basketRequest) return;
      if (data.location.lat != null && data.location.lng != null) { p.set("lat", data.location.lat); p.set("lng", data.location.lng); }
      state.currency = data.currency;
      const full = data.offers.filter((offer) => offer.total != null && !offer.demo);
      const failures = data.sources.filter((source) => !source.ok).length;
      $("basket-compare-message").textContent = `${full.length ? `${full.length} complete non-demo basket option(s) reported by sources.` : "No complete non-demo basket was confirmed by the available sources."} ${failures ? `${failures} item/source check(s) failed; results may be incomplete.` : ""} ${data.offers.some((offer) => offer.demo) ? "Demo examples below are synthetic." : ""}`;
      if (data.skipped_sources?.length) $("basket-compare-message").textContent += " Coordinates are optional for your selected address. Nearby stores and location-dependent delivery providers were skipped; add coordinates if you want those options.";
      $("basket-offers").innerHTML = data.offers.length ? data.offers.map((offer) => basketOffer(offer, p)).join("")
        : '<li class="empty">No provider results. Try a larger radius or check again later.</li>';
    } catch (error) { if (requestId === state.basketRequest) $("basket-compare-message").textContent = error.message; }
    finally { if (requestId === state.basketRequest) $("basket-check").disabled = false; }
  }
  function basketOffer(offer, params) {
    const status = { available: "Reported in stock", missing: "No listing returned", out_of_stock: "Out of stock", unconfirmed: "Stock or price unconfirmed / stale" };
    const directions = offer.kind === "store" && offer.lat != null && offer.lng != null
      ? `https://www.google.com/maps/dir/?api=1&origin=${params.get("lat")},${params.get("lng")}&destination=${offer.lat},${offer.lng}` : null;
    const providerLink = offer.kind === "online" ? offer.items.find((line) => safeLink(line.url))?.url : null;
    const medicineList = offer.items.map((line) => `${line.name} — ${line.qty} ${unitLabel(line)} (shopping quantity, not a dose)`).join("\n");
    return `<li class="item saved-item ${offer.total == null ? "incomplete" : ""}"><div class="page-heading"><h3>${esc(offer.provider)}</h3>
      <strong>${offer.total != null ? money(offer.total) : "Whole-basket total unavailable"}</strong></div>
      <div class="badges"><span class="b">${offer.kind === "online" ? "Online delivery" : offer.fulfilment === "pickup" ? "Store pickup" : "Store delivery"}</span>
      <span class="b ${offer.demo || !offer.complete ? "warn" : ""}">${offer.demo ? "Demo — synthetic" : offer.complete ? "All items reported available" : "Incomplete / unconfirmed basket"}</span><span class="b">Source: ${esc(offer.source)}</span></div>
      <ul class="basket-lines">${offer.items.map((line) => `<li><span>${esc(line.name)} · ${line.qty} ${esc(unitLabel(line))}<br><small>${status[line.status]}${line.observed_at ? ` · Updated ${ago(line.observed_at)}` : ""}</small></span>
      <span>${line.item_price != null ? money(line.item_price) : "Price unknown"}${safeLink(line.url) ? `<br><a href="${safeLink(line.url)}" target="_blank" rel="noopener noreferrer">${offer.demo ? "Demo provider" : "Listing"}</a>` : ""}</span></li>`).join("")}</ul>
      ${offer.total != null ? `<p>Medicine subtotal <b>${money(offer.subtotal)}</b> + Delivery <b>${money(offer.delivery_fee)}</b> + Platform fees <b>${money(offer.platform_fee)}</b> = <b>${money(offer.total)}</b></p>` : ""}
      <p>${offer.fulfilment === "delivery" ? `Estimated delivery: ${offer.eta_minutes != null && offer.total != null ? eta(offer.eta_minutes) : "not available"}` : "Pickup — delivery ETA does not apply"}${offer.distance_km != null ? ` · ${offer.distance_km.toFixed(1)} km estimated road distance` : ""}</p>
      <p class="hint">${esc([offer.address, offer.phone ? `Phone: ${offer.phone}` : "", offer.hours ? `Hours: ${offer.hours}` : ""].filter(Boolean).join(" · "))}</p>
      ${directions ? `<div class="acts"><a href="${esc(directions)}" target="_blank" rel="noopener noreferrer">Directions to store${offer.demo ? " (demo location)" : ""}</a></div>` : ""}
      ${offer.kind === "online" ? `<div class="acts">${providerLink ? `<a href="${safeLink(providerLink)}" target="_blank" rel="noopener noreferrer">${offer.demo ? "Open demo provider website" : `Continue on ${esc(offer.provider)}`}</a>` : ""}<button type="button" data-copy-basket="${esc(medicineList)}">Copy medicine list</button></div>
      <p class="hint">${offer.demo ? "This is a demo, not a real checkout." : "Product links open listings on the provider's site."} Items have not been added to an external basket. Add them there and confirm packs, prescription requirements, fees and delivery time.</p><p class="handoff-status hint" role="status"></p>` : ""}
      <p class="hint">${esc(offer.notes.join(" · "))}</p></li>`;
  }
  $("basket-compare-form").addEventListener("submit", (event) => { event.preventDefault(); checkBasket(); });
  $("checkout-address").addEventListener("change", () => {
    ["lat", "lng"].forEach((id) => { $(`basket-${id}`).value = ""; });
    applyCheckoutAddress(); invalidateBasketOffers(); checkBasket();
  });

  const addressFields = ["label", "recipient", "line1", "line2", "city", "state", "pincode", "lat", "lng"];
  function resetAddressForm() {
    state.addressEdit = null; $("address-form").reset();
    $("address-title").textContent = "Add a home address"; $("address-form-message").textContent = "";
  }
  function addressText(address) {
    return [address.recipient, address.line1, address.line2, address.city, address.state, address.pincode].filter(Boolean).join(", ");
  }
  function applyCheckoutAddress() {
    const address = state.addresses.find((a) => String(a.id) === $("checkout-address").value);
    const hasCoordinates = address && address.lat != null && address.lng != null;
    $("checkout-manual").hidden = !!hasCoordinates;
    ["lat", "lng"].forEach((id) => { $(`basket-${id}`).disabled = !!hasCoordinates; });
    ["lat", "lng"].forEach((id) => { $(`basket-${id}`).required = !address; });
    $("basket-pin").disabled = !!address;
    if (address) $("basket-pin").value = address.pincode;
    $("selected-address").textContent = address ? `${address.label}: ${addressText(address)}${hasCoordinates ? "" : " — Coordinates are optional. Continue with this address and pincode, or add coordinates below to include nearby stores."}` : "Choose a saved address or enter a one-time location below.";
  }
  function renderAddressOptions() {
    const selected = $("checkout-address").value;
    $("checkout-address").innerHTML = '<option value="">Use a one-time location</option>' + state.addresses.map((a) => `<option value="${a.id}">${esc(a.label)} — ${esc(a.line1)}, ${esc(a.city)} ${esc(a.pincode)}</option>`).join("");
    $("checkout-address").value = state.addresses.some((a) => String(a.id) === selected) ? selected : "";
    applyCheckoutAddress();
  }
  async function loadAddresses() {
    const requestId = ++state.addressRequest, userId = state.user?.id;
    $("address-editor").hidden = !state.user;
    $("addresses-message").textContent = state.user ? "Loading…" : "Log in to save and select your home addresses.";
    if (!state.user) return false;
    try {
      const addresses = await api("/api/addresses");
      if (requestId !== state.addressRequest || state.user?.id !== userId) return false;
      state.addresses = addresses; renderAddressOptions();
      $("addresses-message").textContent = addresses.length ? "" : "No addresses saved yet. Add your first home address below.";
      $("addresses-list").innerHTML = addresses.map((a) => `<li class="item saved-item"><h3>${esc(a.label)}</h3><p>${esc(addressText(a))}</p><div class="acts"><button data-address-use="${a.id}">Use for checkout</button><button data-address-edit="${a.id}">Edit</button><button data-address-delete="${a.id}">Delete</button></div></li>`).join("");
      return true;
    } catch (error) { $("addresses-message").textContent = error.message; return false; }
  }
  $("address-form").addEventListener("submit", async (event) => {
    event.preventDefault(); $("address-save").disabled = true;
    const body = Object.fromEntries(addressFields.map((key) => [key, $(`address-${key}`).value.trim()]));
    body.lat = body.lat === "" ? null : Number(body.lat); body.lng = body.lng === "" ? null : Number(body.lng);
    try {
      const saved = await api(state.addressEdit ? `/api/addresses/${state.addressEdit}` : "/api/addresses", state.addressEdit ? "PUT" : "POST", body);
      invalidateBasketOffers(); resetAddressForm(); await loadAddresses();
      $("checkout-address").value = String(saved.id); applyCheckoutAddress();
      $("address-form-message").textContent = "Address saved and selected for your next basket comparison.";
    } catch (error) { $("address-form-message").textContent = error.message; }
    finally { $("address-save").disabled = false; }
  });
  $("address-cancel").addEventListener("click", resetAddressForm);
  $("addresses-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-address-use], [data-address-edit], [data-address-delete]"); if (!button) return;
    const id = button.dataset.addressUse || button.dataset.addressEdit || button.dataset.addressDelete;
    const address = state.addresses.find((a) => String(a.id) === id); if (!address) return;
    if (button.dataset.addressUse) {
      $("checkout-address").value = id; applyCheckoutAddress(); invalidateBasketOffers(); location.hash = "basket"; return;
    }
    if (button.dataset.addressEdit) {
      state.addressEdit = address.id;
      addressFields.forEach((key) => { $(`address-${key}`).value = address[key] ?? ""; });
      $("address-title").textContent = "Edit home address"; $("address-form-message").textContent = "";
      $("address-label").focus(); return;
    }
    button.disabled = true;
    try {
      await api(`/api/addresses/${id}`, "DELETE"); invalidateBasketOffers();
      if (state.addressEdit === address.id) resetAddressForm();
      await loadAddresses();
    } catch (error) { $("addresses-message").textContent = error.message; button.disabled = false; }
  });
  $("address-geo").addEventListener("click", () => {
    if (!navigator.geolocation) { $("address-form-message").textContent = "Enter coordinates manually; geolocation is unavailable."; return; }
    $("address-form-message").textContent = "Finding your location…";
    const userId = state.user?.id, editId = state.addressEdit;
    navigator.geolocation.getCurrentPosition((position) => {
      if (state.user?.id !== userId || state.addressEdit !== editId) return;
      $("address-lat").value = position.coords.latitude.toFixed(5); $("address-lng").value = position.coords.longitude.toFixed(5);
      $("address-form-message").textContent = "Location filled. Check that you are at this home's address before saving.";
    }, () => { $("address-form-message").textContent = "Location permission denied or unavailable. Enter coordinates manually."; }, { timeout: 10000 });
  });
  const recheckBasket = debounce(checkBasket, 500);
  ["lat", "lng", "pin"].forEach((id) => $(`basket-${id}`).addEventListener("input", () => { invalidateBasketOffers(); recheckBasket(); }));
  $("basket-offers").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-basket]"); if (!button) return;
    const status = button.closest("li.item").querySelector(".handoff-status");
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(button.dataset.copyBasket);
      status.textContent = "Medicine list copied. Add these items on the provider's site; quantities are units, not packs.";
    } catch { status.textContent = "Clipboard unavailable. Use the medicine names and quantities shown above to add them on the provider's site."; }
  });
  $("basket-geo").addEventListener("click", () => {
    if (!navigator.geolocation) { $("basket-compare-message").textContent = "Enter latitude and longitude; location sharing is unavailable."; return; }
    invalidateBasketOffers(); $("basket-compare-message").textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition((position) => {
      $("basket-lat").value = position.coords.latitude.toFixed(5); $("basket-lng").value = position.coords.longitude.toFixed(5); checkBasket();
    }, () => { $("basket-compare-message").textContent = "Could not get your location. Enter latitude and longitude instead."; }, { timeout: 10000 });
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-revisit], [data-update], [data-remove]"); if (!button) return;
    if (button.dataset.revisit) { await selectDrug(button.dataset.revisit); $("qty").value = button.dataset.qty; location.hash = "compare"; return; }
    button.disabled = true;
    try {
      if (button.dataset.update) await api("/api/basket", "PUT", { drug_id: button.dataset.update, qty: Number($(`basket-${button.dataset.update}`).value) });
      else await api(`/api/basket/${encodeURIComponent(button.dataset.remove)}`, "DELETE");
      await loadBasket();
    } catch (error) { $("basket-message").textContent = error.message; button.disabled = false; }
  });

  /* ---------- medicine autocomplete ---------- */
  document.querySelectorAll("[data-home-drug]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      await selectDrug(button.dataset.homeDrug);
      button.disabled = false;
      if (state.drug?.id === button.dataset.homeDrug) $("medicine-details").scrollIntoView({
        block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
      });
    });
  });
  const suggest = $("suggest");
  function showSuggestions(items) {
    suggest.innerHTML = items.length
      ? items.map((d) => `<li role="option" data-id="${esc(d.id)}"><button type="button">${esc(d.name)} <small>${esc(packLabel(d))}${d.rx_required ? " · Prescription required" : ""}</small></button></li>`).join("")
      : `<li aria-disabled="true"><small>No match in this starter catalogue. Check spelling or ask a pharmacist; this is not a complete list of medicines in India.</small></li>`;
    suggest.hidden = false;
  }
  document.querySelectorAll("[data-browse-medicines]").forEach((button) => button.addEventListener("click", async () => {
    try {
      const items = await api(`/api/drugs?liquids_only=${button.dataset.browseMedicines === "liquids"}`);
      $("q").focus(); showSuggestions(items);
    } catch (error) { say(error.message); }
  }));
  const search = debounce(async () => {
    const q = $("q").value.trim();
    if (q.length < 2) { suggest.hidden = true; return; }
    try {
      const items = await api(`/api/drugs/search?q=${encodeURIComponent(q)}`);
      showSuggestions(items);
    } catch (error) { suggest.hidden = true; say(error.message); }
  }, 180);
  $("q").addEventListener("input", () => {
    state.drug = null; $("picked").hidden = true; $("medicine-details").hidden = true;
    $("welcome").hidden = false; refreshGo(); search();
  });
  suggest.addEventListener("click", async (e) => {
    const li = e.target.closest("li[data-id]"); if (!li) return;
    suggest.hidden = true;
    await selectDrug(li.dataset.id);
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".field, .catalogue-actions")) suggest.hidden = true; });

  /* ---------- location ---------- */
  $("geo").addEventListener("click", () => {
    if (!navigator.geolocation) return say("This browser can't share location. Enter latitude and longitude instead.");
    say("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (p) => { $("lat").value = p.coords.latitude.toFixed(5); $("lng").value = p.coords.longitude.toFixed(5); say(""); refreshGo(); },
      () => say("Location permission was denied. Enter latitude and longitude instead."),
      { enableHighAccuracy: false, timeout: 10000 });
  });
  ["lat", "lng"].forEach((id) => $(id).addEventListener("input", refreshGo));
  function refreshGo() { $("go").disabled = !(state.drug && $("lat").value && $("lng").value); }

  /* ---------- live search over Server-Sent Events ---------- */
  $("go").addEventListener("click", () => {
    if (!["qty", "radius", "travel", "lat", "lng"].every((id) => $(id).value !== "" && $(id).checkValidity()) || +$("lat").value < -90 || +$("lat").value > 90 || +$("lng").value < -180 || +$("lng").value > 180) return say("Please enter valid quantities and location coordinates.");
    if (state.user) api("/api/history", "POST", { drug_id: state.drug.id, qty: Number($("qty").value) }).catch((error) => say(`History not saved: ${error.message}`));
    if (state.es) state.es.close();
    state.quotes = []; state.sources = {}; state.total = 0; say("");
    const p = new URLSearchParams({ drug_id: state.drug.id, qty: $("qty").value || 1, lat: $("lat").value, lng: $("lng").value,
      radius_km: $("radius").value || 5, travel_cost_per_km: $("travel").value || 0 });
    if ($("pin").value.trim()) p.set("pincode", $("pin").value.trim());
    ["toolbar", "map", "legend"].forEach((id) => ($(id).hidden = false));
    ensureMap();
    renderAlt();
    state.es = new EventSource(`/api/prices/stream?${p}`);
    state.es.addEventListener("meta", (e) => { const m = JSON.parse(e.data); state.total = m.total_sources; state.currency = m.currency; render(); });
    state.es.addEventListener("result", (e) => {
      const r = JSON.parse(e.data);
      state.sources[r.connector] = r; state.quotes.push(...r.quotes); render();
    });
    state.es.addEventListener("done", () => { state.es.close(); render(true); });
    state.es.onerror = () => { state.es.close(); say("Connection lost before all sources replied. Showing what arrived."); render(true); };
    render();
  });

  function renderAlt() {
    const g = (state.drug.alternatives?.same_ingredient_and_strength || []);
    const el = $("alt");
    if (g.length > 1) {
      const cheapest = g[0], priciest = g[g.length - 1];
      el.innerHTML = `Same medicine, different brands: <b>${esc(cheapest.name)}</b> costs ${money(cheapest.pack_price)} per pack against ${money(priciest.pack_price)} for ${esc(priciest.name)}. ${esc(state.drug.alternatives.notice)}`;
      el.hidden = false;
    } else el.hidden = true;
  }

  /* ---------- toolbar ---------- */
  document.querySelectorAll("[data-sort]").forEach((b) => b.addEventListener("click", () => { state.sort = b.dataset.sort; toggle("[data-sort]", b); render(); }));
  document.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => { state.show = b.dataset.show; toggle("[data-show]", b); render(); }));
  $("instock").addEventListener("change", (e) => { state.hideOOS = e.target.checked; render(); });
  function toggle(sel, on) { document.querySelectorAll(sel).forEach((x) => x.classList.toggle("on", x === on)); }

  function sorted(qs) {
    const big = 1e9, a = [...qs];
    const key = { total: (q) => [!q.price_known, q.in_stock === false, q.total],
                  fastest: (q) => [!q.price_known, q.eta_minutes ?? big, q.total],
                  nearest: (q) => [!q.price_known, q.distance_km ?? big, q.total] }[state.sort];
    return a.sort((x, y) => { const kx = key(x), ky = key(y); for (let i = 0; i < kx.length; i++) if (kx[i] !== ky[i]) return kx[i] < ky[i] ? -1 : 1; return 0; });
  }

  /* ---------- rendering ---------- */
  function render(done = false) {
    const names = Object.keys(state.sources);
    const waiting = Math.max(0, state.total - names.length);
    $("sources").innerHTML = names.map((n) => { const s = state.sources[n];
      return `<span class="chip ${s.ok ? "ok" : "err"}" title="${esc(s.error || "")}">${esc(n)}: ${s.ok ? `${s.quotes.length} result${s.quotes.length === 1 ? "" : "s"}${s.cached ? ", cached" : ""}` : "unavailable"}</span>`; }).join("")
      + (!done && waiting ? `<span class="chip wait">${waiting} source${waiting === 1 ? "" : "s"} still loading</span>` : "");

    let qs = state.quotes.filter((q) => (state.show === "all" || q.kind === state.show) && !(state.hideOOS && q.in_stock === false));
    qs = sorted(qs);
    const known = qs.filter((q) => q.price_known && q.in_stock !== false);
    const best = known.length ? known.reduce((m, q) => (q.total < m.total ? q : m)) : null;

    const sum = $("summary");
    if (known.length > 1) {
      const hi = Math.max(...known.map((q) => q.total));
      sum.textContent = `Best all-in cost: ${money(best.total)} at ${best.provider} (${best.fulfilment === "pickup" ? "you collect" : "delivered"}). That is ${money(hi - best.total)} less than the most expensive option.`;
      sum.hidden = false;
    } else sum.hidden = true;

    $("list").innerHTML = qs.length ? qs.map((q) => row(q, q === best)).join("")
      : `<li class="empty">${done ? "Nothing found within this radius. Try a larger radius or a different pack size." : "Waiting for the first source to reply…"}</li>`;
    updateMap(qs);
  }

  function row(q, isBest) {
    const parts = [["item", q.item_price], ["del", q.delivery_fee], ["fee", q.platform_fee], ["trv", q.travel_cost]];
    const sum = parts.reduce((s, p) => s + p[1], 0) || 1;
    const bar = parts.filter((p) => p[1] > 0).map((p) => `<i style="width:${(p[1] / sum * 100).toFixed(1)}%;background:var(--c-${p[0]})"></i>`).join("");
    const line = [`Medicine <b>${money(q.item_price)}</b>`];
    if (q.delivery_fee > 0) line.push(`Delivery <b>${money(q.delivery_fee)}</b>`); else if (q.fulfilment === "delivery") line.push(`Delivery <b>free</b>`);
    if (q.platform_fee > 0) line.push(`Fees <b>${money(q.platform_fee)}</b>`);
    if (q.travel_cost > 0) line.push(`Your travel <b>${money(q.travel_cost)}</b>`);
    const badges = [
      isBest ? `<span class="b best">Lowest total</span>` : "",
      `<span class="b">${q.kind === "online" ? "Online, delivered" : q.fulfilment === "pickup" ? "Store, you collect" : "Store, delivers"}</span>`,
      q.in_stock === false ? `<span class="b bad">Out of stock</span>` : q.in_stock === true ? `<span class="b">In stock</span>` : `<span class="b warn">Stock unknown</span>`,
      !q.price_known ? `<span class="b warn">Price unconfirmed</span>` : "",
      `<span class="b ${q.source === "demo" ? "warn" : ""}" title="Confidence ${Math.round(q.confidence * 100)}%">Source: ${esc(q.source)}</span>`,
    ].join("");
    const meta = [q.distance_km != null ? `${q.distance_km.toFixed(1)} km away` : "", q.eta_minutes != null ? `Arrives ${eta(q.eta_minutes)}` : "",
      q.hours ? `Hours ${esc(q.hours)}` : "", `Updated ${ago(q.observed_at)}`, q.phone ? `Phone ${esc(q.phone)}` : ""].filter(Boolean).join("</span><span>");
    const notes = q.notes.length ? `<span>${esc(q.notes.join(" · "))}</span>` : "";
    const acts = [
      q.kind === "store" && q.lat != null ? `<a target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${q.lat},${q.lng}">Directions</a><button data-focus="${esc(q.id)}">Show on map</button>` : "",
      safeLink(q.url) ? `<a target="_blank" rel="noopener noreferrer" href="${safeLink(q.url)}">${q.source === "demo" ? "Provider website (demo listing)" : q.kind === "online" ? "View product listing" : "Open provider"}</a>` : "",
    ].join("");
    return `<li class="item ${isBest ? "best" : ""} ${q.in_stock === false ? "dim" : ""}">
      <div><h3>${esc(q.provider)}</h3><div class="badges">${badges}</div></div>
      <div class="total"><div class="n">${money(q.total)}</div><div class="s">${q.fulfilment === "pickup" ? "including your travel" : "delivered"}</div></div>
      <div class="stack" aria-hidden="true">${bar}</div>
      <div class="parts">${line.join(" + ")}</div>
      <div class="meta"><span>${meta}</span>${notes}</div>
      <div class="acts">${acts}</div></li>`;
  }

  $("list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-focus]"); if (!b) return;
    const m = state.markers[b.dataset.focus]; if (m && state.map) { state.map.setView(m.getLatLng(), 16); m.openPopup(); $("map").scrollIntoView({ behavior: "smooth", block: "center" }); }
  });

  /* ---------- map ---------- */
  function ensureMap() {
    if (state.map || typeof L === "undefined") return;
    state.map = L.map("map").setView([+$("lat").value, +$("lng").value], 14);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }).addTo(state.map);
    state.layer = L.layerGroup().addTo(state.map);
  }
  function updateMap(qs) {
    if (!state.map) return;
    state.layer.clearLayers(); state.markers = {};
    const me = L.circleMarker([+$("lat").value, +$("lng").value], { radius: 8, color: "#14312c", fillColor: "#14312c", fillOpacity: 1 }).bindPopup("You are here");
    me.addTo(state.layer);
    const pts = [me.getLatLng()];
    qs.filter((q) => q.kind === "store" && q.lat != null && q.fulfilment === "pickup").forEach((q) => {
      const m = L.marker([q.lat, q.lng]).bindPopup(`<b>${esc(q.provider)}</b><br>${q.price_known ? money(q.total) + " all-in" : "Price unconfirmed"}<br>${q.distance_km.toFixed(1)} km`);
      m.addTo(state.layer); state.markers[q.id] = m; pts.push(m.getLatLng());
    });
    if (pts.length > 1) state.map.fitBounds(L.latLngBounds(pts).pad(0.2));
    setTimeout(() => state.map.invalidateSize(), 50);
  }
  (async () => {
    try { await api("/api/health"); }
    catch (error) { say(error.message); updateAccount(); await route(); return; }
    try { state.user = await api("/api/auth/me"); } catch { state.user = null; }
    updateAccount(); if (state.user) await loadBasket(); await route();
  })();
})();
