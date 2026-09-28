/* =====================================================================
   Material Design 3 · Expressive — Web Components
   ---------------------------------------------------------------------
   Framework-free custom elements. Each renders into a Shadow DOM and
   reads the global --md-sys-* tokens (custom properties pierce the
   shadow boundary), so theming + dynamic color apply automatically.

   Elements:
     <md-button>          variant filled|tonal|elevated|outlined|text
                          size xs|s|m|l|xl · icon · trailing-icon · href
     <md-icon-button>     variant standard|filled|tonal|outlined · toggle
     <md-fab>             size small|medium|large · variant · extended · icon
     <md-chip>            variant assist|filter|input|suggestion · removable
     <md-switch>          selected · icons · disabled
     <md-checkbox>        checked · indeterminate · disabled
     <md-radio>           name · value · checked
     <md-slider>          min max value step · labeled
     <md-text-field>      variant filled|outlined · label · icons · error
     <md-card>            variant elevated|filled|outlined
     <md-menu> + <md-menu-item>
     <md-tabs> + <md-tab> variant primary|secondary
     <md-list> + <md-list-item>
     <md-divider>
     <md-progress>        variant linear|circular · value · indeterminate
     <md-dialog>          open · slots: headline, default, actions
     <md-segmented-button> + items via <button data-value>
   ===================================================================== */
(function () {
  'use strict';

  const SPRING_FAST = '350ms cubic-bezier(0.42,1.67,0.21,0.90)';
  const SPRING_STD = '500ms cubic-bezier(0.38,1.21,0.22,1.00)';
  const EASE_STD = '200ms cubic-bezier(0.2,0,0,1)';

  // Shared style-layer + ripple used across interactive components.
  const STATE_LAYER = `
    .state {
      position:absolute; inset:0; border-radius:inherit;
      background:currentColor; opacity:0; pointer-events:none;
      transition:opacity var(--md-sys-motion-spring-default-effects, ${EASE_STD});
    }
    :host(:not([disabled])) .surface:hover .state { opacity:0.08; }
    :host(:not([disabled])) .surface:focus-visible .state { opacity:0.10; }
    .ripple {
      position:absolute; border-radius:50%; transform:scale(0);
      background:currentColor; opacity:0.12; pointer-events:none;
      animation:ripple 500ms cubic-bezier(0.2,0,0,1);
    }
    @keyframes ripple { to { transform:scale(2.2); opacity:0; } }
    @media (prefers-reduced-motion: reduce){ .ripple{ animation-duration:1ms; } }
  `;

  function addRipple(host, surface) {
    surface.addEventListener('pointerdown', e => {
      if (host.hasAttribute('disabled')) return;
      const r = surface.getBoundingClientRect();
      const size = Math.max(r.width, r.height);
      const rip = document.createElement('span');
      rip.className = 'ripple';
      rip.style.width = rip.style.height = size + 'px';
      rip.style.left = (e.clientX - r.left - size / 2) + 'px';
      rip.style.top = (e.clientY - r.top - size / 2) + 'px';
      surface.appendChild(rip);
      rip.addEventListener('animationend', () => rip.remove());
    });
  }

  const define = (name, cls) => { if (!customElements.get(name)) customElements.define(name, cls); };

  /* ================================================================
     md-button
     ================================================================ */
  class MdButton extends HTMLElement {
    static get observedAttributes() { return ['variant', 'size', 'disabled', 'trailing-icon', 'icon', 'href']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const variant = this.getAttribute('variant') || 'filled';
      const size = this.getAttribute('size') || 's';
      const icon = this.getAttribute('icon');
      const trailing = this.hasAttribute('trailing-icon');
      const href = this.getAttribute('href');
      const heights = { xs: 32, s: 40, m: 48, l: 56, xl: 64 };
      const h = heights[size] || 40;
      const pad = { xs: 12, s: 16, m: 24, l: 32, xl: 40 }[size] || 16;
      const fs = { xs: 14, s: 14, m: 16, l: 20, xl: 24 }[size] || 14;
      const bg = {
        filled: 'var(--md-sys-color-primary)', tonal: 'var(--md-sys-color-secondary-container)',
        elevated: 'var(--md-sys-color-surface-container-low)', outlined: 'transparent', text: 'transparent',
      }[variant];
      const fg = {
        filled: 'var(--md-sys-color-on-primary)', tonal: 'var(--md-sys-color-on-secondary-container)',
        elevated: 'var(--md-sys-color-primary)', outlined: 'var(--md-sys-color-primary)', text: 'var(--md-sys-color-primary)',
      }[variant];
      const border = variant === 'outlined' ? '1px solid var(--md-sys-color-outline)' : 'none';
      const shadow = variant === 'elevated' ? 'var(--md-sys-elevation-level1)' : 'none';
      const tag = href ? 'a' : 'button';
      const iconSpan = icon ? `<span class="md-ic" aria-hidden="true">${icon}</span>` : '';
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; vertical-align:middle; }
          :host([disabled]){ pointer-events:none; }
          .surface{
            position:relative; overflow:hidden; box-sizing:border-box;
            display:inline-flex; align-items:center; justify-content:center; gap:8px;
            height:${h}px; padding:0 ${pad}px; min-width:48px;
            border:${border}; background:${bg}; color:${fg};
            border-radius:var(--md-sys-shape-corner-full);
            box-shadow:${shadow}; cursor:pointer; text-decoration:none;
            font:500 ${fs}px/1 var(--md-sys-typescale-font-plain); letter-spacing:.1px;
            transition:transform .13s cubic-bezier(.2,.8,.2,1), box-shadow ${EASE_STD}, background ${EASE_STD};
            -webkit-tap-highlight-color:transparent;
          }
          /* Press: scale-down halus + ripple (bukan shape morph) */
          .surface:active{ transform:scale(.94); }
          :host([disabled]) .surface{
            background:${variant === 'outlined' || variant === 'text' ? 'transparent' : 'color-mix(in srgb, var(--md-sys-color-on-surface) 12%, transparent)'};
            color:color-mix(in srgb, var(--md-sys-color-on-surface) 38%, transparent);
            border-color:color-mix(in srgb, var(--md-sys-color-on-surface) 12%, transparent);
            box-shadow:none; cursor:default;
          }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:${Math.round(fs * 1.3)}px; line-height:1;
                  font-variation-settings:'FILL' 0,'wght' 400,'opsz' ${Math.round(fs*1.3)}; }
          .lbl{ display:inline-flex; align-items:center; white-space:nowrap; }
          ${STATE_LAYER}
        </style>
        <${tag} class="surface" ${href ? `href="${href}"` : ''} ${this.hasAttribute('disabled') ? 'disabled aria-disabled="true"' : ''} part="button">
          <span class="state"></span>
          ${!trailing ? iconSpan : ''}
          <span class="lbl"><slot></slot></span>
          ${trailing ? iconSpan : ''}
        </${tag}>`;
      addRipple(this, root.querySelector('.surface'));
    }
  }
  define('md-button', MdButton);

  /* ================================================================
     md-icon-button
     ================================================================ */
  class MdIconButton extends HTMLElement {
    static get observedAttributes() { return ['variant', 'disabled', 'toggle', 'selected']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const variant = this.getAttribute('variant') || 'standard';
      const selected = this.hasAttribute('selected');
      const toggle = this.hasAttribute('toggle');
      const styles = {
        standard: ['transparent', 'var(--md-sys-color-on-surface-variant)'],
        filled: [selected || !toggle ? 'var(--md-sys-color-primary)' : 'var(--md-sys-color-surface-container-highest)',
                 selected || !toggle ? 'var(--md-sys-color-on-primary)' : 'var(--md-sys-color-primary)'],
        tonal: ['var(--md-sys-color-secondary-container)', 'var(--md-sys-color-on-secondary-container)'],
        outlined: ['transparent', 'var(--md-sys-color-on-surface-variant)'],
      };
      const [bg, fg] = styles[variant] || styles.standard;
      const border = variant === 'outlined' ? '1px solid var(--md-sys-color-outline)' : 'none';
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .surface{
            position:relative; overflow:hidden; box-sizing:border-box;
            width:40px; height:40px; display:inline-flex; align-items:center; justify-content:center;
            border:${border}; background:${bg}; color:${fg}; cursor:pointer;
            border-radius:var(--md-sys-shape-corner-full);
            transition:transform .13s cubic-bezier(.2,.8,.2,1), background ${EASE_STD};
            -webkit-tap-highlight-color:transparent;
          }
          .surface:active{ transform:scale(.92); }
          :host([disabled]){ pointer-events:none; }
          :host([disabled]) .surface{ color:color-mix(in srgb,var(--md-sys-color-on-surface) 38%,transparent); background:transparent; border-color:color-mix(in srgb,var(--md-sys-color-on-surface) 12%,transparent);}
          ::slotted(*), .md-ic{ font-family:'Material Symbols Outlined'; font-size:24px; line-height:1;
            font-variation-settings:'FILL' ${selected ? 1 : 0},'wght' 400,'opsz' 24; }
          ${STATE_LAYER}
        </style>
        <button class="surface" part="button" aria-pressed="${toggle ? selected : 'undefined'}" ${this.hasAttribute('disabled') ? 'disabled' : ''}>
          <span class="state"></span><slot></slot>
        </button>`;
      const btn = root.querySelector('.surface');
      addRipple(this, btn);
      if (toggle) btn.addEventListener('click', () => { this.toggleAttribute('selected'); this.dispatchEvent(new Event('change')); });
    }
  }
  define('md-icon-button', MdIconButton);

  /* ================================================================
     md-fab (+ extended)
     ================================================================ */
  class MdFab extends HTMLElement {
    static get observedAttributes() { return ['size', 'variant', 'extended', 'icon', 'label']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const size = this.getAttribute('size') || 'medium';
      const variant = this.getAttribute('variant') || 'primary';
      const extended = this.hasAttribute('extended');
      const icon = this.getAttribute('icon') || 'add';
      const label = this.getAttribute('label') || '';
      const dims = { small: 40, medium: 56, large: 96 }[size] || 56;
      const iconSz = { small: 24, medium: 24, large: 36 }[size] || 24;
      const radius = { small: 'var(--md-sys-shape-corner-medium)', medium: 'var(--md-sys-shape-corner-large)', large: 'var(--md-sys-shape-corner-extra-large)' }[size];
      const colors = {
        surface: ['var(--md-sys-color-surface-container-high)', 'var(--md-sys-color-primary)'],
        primary: ['var(--md-sys-color-primary-container)', 'var(--md-sys-color-on-primary-container)'],
        secondary: ['var(--md-sys-color-secondary-container)', 'var(--md-sys-color-on-secondary-container)'],
        tertiary: ['var(--md-sys-color-tertiary-container)', 'var(--md-sys-color-on-tertiary-container)'],
      }[variant] || ['var(--md-sys-color-primary-container)', 'var(--md-sys-color-on-primary-container)'];
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .surface{
            position:relative; overflow:hidden; box-sizing:border-box; cursor:pointer; border:none;
            display:inline-flex; align-items:center; justify-content:center; gap:12px;
            ${extended ? `height:56px; padding:0 20px; border-radius:var(--md-sys-shape-corner-large);`
                       : `width:${dims}px; height:${dims}px; border-radius:${radius};`}
            background:${colors[0]}; color:${colors[1]};
            box-shadow:var(--md-sys-elevation-level3);
            font:500 14px/1 var(--md-sys-typescale-font-plain); letter-spacing:.1px;
            transition:transform .13s cubic-bezier(.2,.8,.2,1), box-shadow ${EASE_STD};
            -webkit-tap-highlight-color:transparent;
          }
          .surface:hover{ box-shadow:var(--md-sys-elevation-level4); }
          .surface:active{ transform:scale(.92); }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:${iconSz}px; line-height:1; font-variation-settings:'opsz' ${iconSz}; }
          ${STATE_LAYER}
        </style>
        <button class="surface" part="button" aria-label="${label || icon}">
          <span class="state"></span>
          <span class="md-ic" aria-hidden="true">${icon}</span>
          ${extended && label ? `<span>${label}</span>` : ''}
        </button>`;
      addRipple(this, root.querySelector('.surface'));
    }
  }
  define('md-fab', MdFab);

  /* ================================================================
     md-chip
     ================================================================ */
  class MdChip extends HTMLElement {
    static get observedAttributes() { return ['variant', 'selected', 'removable', 'icon', 'disabled']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const variant = this.getAttribute('variant') || 'assist';
      const selected = this.hasAttribute('selected');
      const removable = this.hasAttribute('removable');
      const icon = this.getAttribute('icon');
      const filterCheck = variant === 'filter' && selected;
      const bg = selected && (variant === 'filter' || variant === 'input')
        ? 'var(--md-sys-color-secondary-container)' : 'transparent';
      const fg = selected && (variant === 'filter' || variant === 'input')
        ? 'var(--md-sys-color-on-secondary-container)' : 'var(--md-sys-color-on-surface-variant)';
      const border = bg === 'transparent' ? '1px solid var(--md-sys-color-outline-variant)' : 'none';
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .surface{
            position:relative; overflow:hidden; box-sizing:border-box; cursor:pointer;
            display:inline-flex; align-items:center; gap:8px; height:32px; padding:0 16px;
            border:${border}; background:${bg}; color:${fg};
            border-radius:var(--md-sys-shape-corner-small);
            font:var(--md-sys-typescale-label-large); letter-spacing:.1px;
            transition:transform .13s cubic-bezier(.2,.8,.2,1), background ${EASE_STD};
            -webkit-tap-highlight-color:transparent;
          }
          .surface:active{ transform:scale(.96); }
          :host([disabled]){ pointer-events:none; opacity:.38; }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:18px; line-height:1; font-variation-settings:'opsz' 20; margin-left:-4px; }
          .rm{ font-family:'Material Symbols Outlined'; font-size:18px; margin-right:-6px; cursor:pointer; }
          ${STATE_LAYER}
        </style>
        <button class="surface" part="chip" role="${variant === 'filter' ? 'checkbox' : 'button'}" aria-checked="${selected}">
          <span class="state"></span>
          ${filterCheck ? '<span class="md-ic">check</span>' : (icon ? `<span class="md-ic">${icon}</span>` : '')}
          <slot></slot>
          ${removable ? '<span class="rm" part="remove">close</span>' : ''}
        </button>`;
      const surf = root.querySelector('.surface');
      addRipple(this, surf);
      if (variant === 'filter' || variant === 'input') {
        surf.addEventListener('click', e => {
          if (e.target.classList.contains('rm')) return;
          this.toggleAttribute('selected'); this.dispatchEvent(new Event('change'));
        });
      }
      const rm = root.querySelector('.rm');
      if (rm) rm.addEventListener('click', e => { e.stopPropagation(); this.dispatchEvent(new Event('remove')); this.remove(); });
    }
  }
  define('md-chip', MdChip);

  /* ================================================================
     md-switch
     ================================================================ */
  class MdSwitch extends HTMLElement {
    static get observedAttributes() { return ['selected', 'disabled']; }
    get selected() { return this.hasAttribute('selected'); }
    set selected(v) { this.toggleAttribute('selected', !!v); }
    connectedCallback() {
      // Build the DOM ONCE. State is expressed via :host attributes so the
      // browser animates the *same* thumb element on toggle — like Flutter's
      // Switch, which drives a single AnimationController instead of rebuilding.
      if (this._built) return;
      this._built = true;
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .track{
            position:relative; box-sizing:border-box; width:52px; height:32px; cursor:pointer;
            border-radius:var(--md-sys-shape-corner-full);
            background:var(--md-sys-color-surface-container-highest);
            border:2px solid var(--md-sys-color-outline);
            transition:background 250ms cubic-bezier(0.2,0,0,1), border-color 250ms cubic-bezier(0.2,0,0,1);
            padding:0; -webkit-tap-highlight-color:transparent;
          }
          .handle{
            position:absolute; top:50%; left:0;
            width:16px; height:16px; border-radius:50%;
            background:var(--md-sys-color-outline);
            display:grid; place-items:center;
            /* translateX carries the slide; width/height carry the grow. One
               curve, GPU-friendly transform → a smooth continuous glide. */
            transform:translate(6px,-50%);
            transition:transform 300ms cubic-bezier(0.2,0,0,1),
                       width 300ms cubic-bezier(0.2,0,0,1),
                       height 300ms cubic-bezier(0.2,0,0,1),
                       background 250ms cubic-bezier(0.2,0,0,1);
          }
          /* A switch with a thumbIcon keeps the larger 24dp thumb even when off. */
          :host([icons]) .handle{ width:24px; height:24px; transform:translate(4px,-50%); }
          /* Selected: track fills, thumb grows to 24dp and slides right. */
          :host([selected]) .track{ background:var(--md-sys-color-primary); border-color:var(--md-sys-color-primary); }
          :host([selected]) .handle{ width:24px; height:24px; background:var(--md-sys-color-on-primary);
            transform:translate(24px,-50%); }
          /* Pressed thumb grows to 28dp (stays circular, no jump). */
          .track:active .handle{ width:28px; height:28px; }
          :host(:not([selected])) .track:active .handle{ transform:translate(2px,-50%); }
          :host([selected]) .track:active .handle{ transform:translate(22px,-50%); }
          .ic{ position:absolute; font-family:'Material Symbols Outlined'; font-size:16px; line-height:1;
            opacity:0; transition:opacity 100ms cubic-bezier(0.2,0,0,1); }
          .ic.on{ color:var(--md-sys-color-on-primary-container); }
          .ic.off{ color:var(--md-sys-color-surface-container-highest); }
          :host([icons]:not([selected])) .ic.off{ opacity:1; }
          :host([icons][selected]) .ic.on{ opacity:1; }
          :host([disabled]){ pointer-events:none; opacity:.4; }
          @media (prefers-reduced-motion: reduce){ .track,.handle,.ic{ transition-duration:1ms; } }
        </style>
        <button class="track" role="switch" part="switch" aria-checked="${this.selected}"
          ${this.hasAttribute('disabled') ? 'disabled' : ''}>
          <span class="handle">
            <span class="ic off" aria-hidden="true">close</span>
            <span class="ic on" aria-hidden="true">check</span>
          </span>
        </button>`;
      root.querySelector('.track').addEventListener('click', () => {
        if (this.hasAttribute('disabled')) return;
        this.toggleAttribute('selected');           // only flips an attribute → CSS animates
        this.dispatchEvent(new Event('change'));
      });
    }
    attributeChangedCallback(name) {
      // Reflect state to ARIA only; never rebuild the DOM (that would kill the transition).
      if (!this.shadowRoot) return;
      const btn = this.shadowRoot.querySelector('.track');
      if (!btn) return;
      if (name === 'selected') btn.setAttribute('aria-checked', this.selected);
      if (name === 'disabled') this.hasAttribute('disabled') ? btn.setAttribute('disabled', '') : btn.removeAttribute('disabled');
    }
  }
  define('md-switch', MdSwitch);

  /* ================================================================
     md-checkbox
     ================================================================ */
  class MdCheckbox extends HTMLElement {
    static get observedAttributes() { return ['checked', 'indeterminate', 'disabled']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    get checked() { return this.hasAttribute('checked'); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const on = this.hasAttribute('checked') || this.hasAttribute('indeterminate');
      const ind = this.hasAttribute('indeterminate');
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .box{ position:relative; width:18px; height:18px; margin:11px; cursor:pointer;
            border-radius:2px;
            border:2px solid ${on ? 'var(--md-sys-color-primary)' : 'var(--md-sys-color-on-surface-variant)'};
            background:${on ? 'var(--md-sys-color-primary)' : 'transparent'};
            transition:background ${EASE_STD}, border-color ${EASE_STD}; }
          .box::after{ content:'${ind ? '\\e15b' : '\\e5ca'}'; font-family:'Material Symbols Outlined';
            position:absolute; inset:-2px; display:${on ? 'flex' : 'none'}; align-items:center; justify-content:center;
            font-size:18px; color:var(--md-sys-color-on-primary); font-variation-settings:'wght' 600; }
          :host([disabled]){ pointer-events:none; opacity:.38; }
        </style>
        <button class="box" role="checkbox" aria-checked="${ind ? 'mixed' : on}" part="checkbox" ${this.hasAttribute('disabled') ? 'disabled' : ''}></button>`;
      root.querySelector('.box').addEventListener('click', () => {
        if (this.hasAttribute('disabled')) return;
        this.removeAttribute('indeterminate'); this.toggleAttribute('checked'); this.dispatchEvent(new Event('change'));
      });
    }
  }
  define('md-checkbox', MdCheckbox);

  /* ================================================================
     md-radio
     ================================================================ */
  class MdRadio extends HTMLElement {
    static get observedAttributes() { return ['checked', 'disabled', 'name', 'value']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const on = this.hasAttribute('checked');
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .r{ position:relative; width:20px; height:20px; margin:10px; cursor:pointer; border-radius:50%;
            border:2px solid ${on ? 'var(--md-sys-color-primary)' : 'var(--md-sys-color-on-surface-variant)'};
            transition:border-color ${EASE_STD}; }
          .r::after{ content:''; position:absolute; inset:3px; border-radius:50%;
            background:var(--md-sys-color-primary); transform:scale(${on ? 1 : 0});
            transition:transform ${SPRING_FAST}; }
          :host([disabled]){ pointer-events:none; opacity:.38; }
        </style>
        <button class="r" role="radio" aria-checked="${on}" part="radio" ${this.hasAttribute('disabled') ? 'disabled' : ''}></button>`;
      root.querySelector('.r').addEventListener('click', () => {
        if (this.hasAttribute('disabled') || this.hasAttribute('checked')) return;
        const name = this.getAttribute('name');
        if (name) document.querySelectorAll(`md-radio[name="${name}"]`).forEach(r => r.removeAttribute('checked'));
        this.setAttribute('checked', ''); this.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }
  }
  define('md-radio', MdRadio);

  /* ================================================================
     md-slider
     ================================================================ */
  class MdSlider extends HTMLElement {
    static get observedAttributes() { return ['min', 'max', 'value', 'step', 'labeled', 'disabled']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback(n) { if (this.shadowRoot && n !== 'value') this.render(); else if (this.shadowRoot) this.update(); }
    get value() { return parseFloat(this.getAttribute('value') || '0'); }
    set value(v) { this.setAttribute('value', v); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const labeled = this.hasAttribute('labeled');
      root.innerHTML = `
        <style>
          :host{ display:block; padding:16px 0; --p:0%; }
          .wrap{ position:relative; height:44px; display:flex; align-items:center; }
          .track{ position:relative; flex:1; height:16px; display:flex; align-items:center; }
          .rail{ position:absolute; left:0; right:0; height:16px; border-radius:var(--md-sys-shape-corner-full);
            background:var(--md-sys-color-secondary-container); overflow:hidden; }
          .active{ position:absolute; left:0; height:16px; width:var(--p);
            background:var(--md-sys-color-primary); border-radius:var(--md-sys-shape-corner-full);
            transition:width ${EASE_STD}; }
          .handle{ position:absolute; left:var(--p); top:50%; transform:translate(-50%,-50%);
            width:4px; height:44px; border-radius:var(--md-sys-shape-corner-full);
            background:var(--md-sys-color-primary); transition:left ${EASE_STD}, height ${SPRING_FAST};
            box-shadow:0 0 0 6px transparent; }
          .wrap:active .handle{ height:52px; }
          input{ position:absolute; inset:0; width:100%; margin:0; opacity:0; cursor:pointer; height:44px; }
          .lbl{ position:absolute; left:var(--p); bottom:100%; transform:translateX(-50%);
            background:var(--md-sys-color-primary); color:var(--md-sys-color-on-primary);
            padding:4px 10px; border-radius:var(--md-sys-shape-corner-full);
            font:var(--md-sys-typescale-label-medium); opacity:0; transition:opacity ${EASE_STD};
            white-space:nowrap; pointer-events:none; }
          .wrap:active .lbl{ opacity:${labeled ? 1 : 0}; }
          :host([disabled]){ pointer-events:none; opacity:.38; }
        </style>
        <div class="wrap">
          <div class="track">
            <div class="rail"></div><div class="active"></div>
          </div>
          <div class="handle"></div>
          ${labeled ? '<div class="lbl">0</div>' : ''}
          <input type="range" min="${this.getAttribute('min') || 0}" max="${this.getAttribute('max') || 100}"
                 step="${this.getAttribute('step') || 'any'}" value="${this.getAttribute('value') || 0}"
                 aria-label="slider">
        </div>`;
      const input = root.querySelector('input');
      input.addEventListener('input', () => { this.setAttribute('value', input.value); this.update(); this.dispatchEvent(new Event('input')); });
      this.update();
    }
    update() {
      const root = this.shadowRoot; if (!root) return;
      const min = parseFloat(this.getAttribute('min') || 0), max = parseFloat(this.getAttribute('max') || 100);
      const v = parseFloat(this.getAttribute('value') || 0);
      const p = ((v - min) / (max - min)) * 100;
      root.host.style.setProperty('--p', p + '%');
      const lbl = root.querySelector('.lbl'); if (lbl) lbl.textContent = v;
    }
  }
  define('md-slider', MdSlider);

  /* ================================================================
     md-text-field
     ================================================================ */
  class MdTextField extends HTMLElement {
    static get observedAttributes() { return ['variant', 'label', 'value', 'type', 'supporting-text', 'error', 'error-text', 'leading-icon', 'trailing-icon', 'disabled']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    get value() { return this.shadowRoot ? this.shadowRoot.querySelector('input,textarea').value : this.getAttribute('value'); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const variant = this.getAttribute('variant') || 'outlined';
      const label = this.getAttribute('label') || '';
      const val = this.getAttribute('value') || '';
      const type = this.getAttribute('type') || 'text';
      const support = this.getAttribute('supporting-text') || '';
      const error = this.hasAttribute('error');
      const errorText = this.getAttribute('error-text') || '';
      const lead = this.getAttribute('leading-icon');
      const trail = this.getAttribute('trailing-icon');
      const outlined = variant === 'outlined';
      const bg = outlined ? 'transparent' : 'var(--md-sys-color-surface-container-highest)';
      const accent = error ? 'var(--md-sys-color-error)' : 'var(--md-sys-color-primary)';
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; flex-direction:column; min-width:210px; }
          .field{ box-sizing:border-box; position:relative; display:flex; align-items:center; gap:12px; min-height:56px; padding:0 16px;
            background:${bg}; cursor:text;
            border-radius:${outlined ? 'var(--md-sys-shape-corner-extra-small)' : 'var(--md-sys-shape-corner-extra-small-top)'};
            ${outlined ? `border:1px solid ${error ? 'var(--md-sys-color-error)' : 'var(--md-sys-color-outline)'};`
                       : `border-bottom:1px solid ${error ? 'var(--md-sys-color-error)' : 'var(--md-sys-color-on-surface-variant)'};`}
            transition:border-color ${EASE_STD}, box-shadow ${EASE_STD}, background ${EASE_STD}; }
          .field:focus-within{ ${outlined ? `border:2px solid ${accent}; padding:0 15px; box-shadow:0 0 0 4px color-mix(in srgb, ${accent} 13%, transparent);` : `border-bottom:2px solid ${accent};`} }
          label{ position:absolute; left:${lead ? '48px' : '16px'}; top:50%; transform:translateY(-50%);
            color:${error ? 'var(--md-sys-color-error)' : 'var(--md-sys-color-on-surface-variant)'};
            font:var(--md-sys-typescale-body-large); pointer-events:none; background:transparent; padding:0 4px;
            transition:all ${EASE_STD}; }
          .field:focus-within label, label.float{
            top:${outlined ? '0' : '8px'}; transform:translateY(-50%) scale(.75); transform-origin:left;
            left:${outlined ? '12px' : '12px'}; color:${accent};
            ${outlined ? 'background:var(--md-field-notch, var(--md-sys-color-surface));' : ''} }
          input,textarea{ flex:1; border:none; outline:none; background:transparent; color:var(--md-sys-color-on-surface);
            font:var(--md-sys-typescale-body-large); padding:16px 0 8px; min-width:0; resize:vertical; font-family:inherit; }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:24px; color:var(--md-sys-color-on-surface-variant); }
          .support{ font:var(--md-sys-typescale-body-small); color:${error ? 'var(--md-sys-color-error)' : 'var(--md-sys-color-on-surface-variant)'};
            padding:4px 16px 0; }
          :host([disabled]){ opacity:.38; pointer-events:none; }
        </style>
        <div class="field" part="field">
          ${lead ? `<span class="md-ic">${lead}</span>` : ''}
          ${label ? `<label class="${(val || type === 'date') ? 'float' : ''}">${label}</label>` : ''}
          ${type === 'textarea'
            ? `<textarea rows="3">${val}</textarea>`
            : `<input type="${type}" value="${val}">`}
          ${trail ? `<span class="md-ic">${trail}</span>` : ''}
        </div>
        ${(error && errorText) || support ? `<div class="support">${error && errorText ? errorText : support}</div>` : ''}`;
      const inp = root.querySelector('input,textarea');
      const lab = root.querySelector('label');
      inp.addEventListener('input', () => { if (lab) lab.classList.toggle('float', !!inp.value || type === 'date'); this.dispatchEvent(new Event('input')); });
      root.querySelector('.field').addEventListener('click', () => inp.focus());
    }
  }
  define('md-text-field', MdTextField);

  /* ================================================================
     md-card
     ================================================================ */
  class MdCard extends HTMLElement {
    static get observedAttributes() { return ['variant']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const v = this.getAttribute('variant') || 'elevated';
      const map = {
        elevated: ['var(--md-sys-color-surface-container-low)', 'var(--md-sys-elevation-level1)', 'none'],
        filled: ['var(--md-sys-color-surface-container-highest)', 'var(--md-sys-elevation-level0)', 'none'],
        outlined: ['var(--md-sys-color-surface)', 'var(--md-sys-elevation-level0)', '1px solid var(--md-sys-color-outline-variant)'],
      }[v];
      root.innerHTML = `
        <style>
          :host{ display:block; }
          .card{ background:${map[0]}; box-shadow:${map[1]}; border:${map[2]};
            border-radius:var(--md-sys-shape-corner-medium); padding:16px;
            color:var(--md-sys-color-on-surface); transition:box-shadow ${EASE_STD}; }
        </style>
        <div class="card" part="card"><slot></slot></div>`;
    }
  }
  define('md-card', MdCard);

  /* ================================================================
     md-divider
     ================================================================ */
  class MdDivider extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      const inset = this.hasAttribute('inset');
      root.innerHTML = `<style>:host{ display:block; }
        hr{ border:none; height:1px; background:var(--md-sys-color-outline-variant);
        margin:0 ${inset ? '16px' : '0'}; }</style><hr>`;
    }
  }
  define('md-divider', MdDivider);

  /* ================================================================
     md-menu (+ md-menu-item) — anchored dropdown
     ================================================================ */
  class MdMenu extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `
        <style>
          :host{ position:absolute; z-index:1000; display:none; }
          :host([open]){ display:block; }
          .menu{ min-width:180px; background:var(--md-sys-color-surface-container);
            border-radius:var(--md-sys-shape-corner-extra-small); padding:8px 0;
            box-shadow:var(--md-sys-elevation-level2);
            transform-origin:top; animation:open ${SPRING_FAST}; }
          @keyframes open{ from{ opacity:0; transform:scaleY(.8); } to{ opacity:1; transform:scaleY(1); } }
        </style>
        <div class="menu" role="menu"><slot></slot></div>`;
    }
    show() { this.setAttribute('open', ''); }
    close() { this.removeAttribute('open'); }
  }
  define('md-menu', MdMenu);

  class MdMenuItem extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      const icon = this.getAttribute('icon');
      root.innerHTML = `
        <style>
          :host{ display:block; }
          .item{ position:relative; overflow:hidden; display:flex; align-items:center; gap:12px;
            min-height:48px; padding:0 16px; cursor:pointer; color:var(--md-sys-color-on-surface);
            font:var(--md-sys-typescale-body-large); }
          .item:hover{ background:color-mix(in srgb, var(--md-sys-color-on-surface) 8%, transparent); }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:24px; color:var(--md-sys-color-on-surface-variant); }
        </style>
        <div class="item" role="menuitem">${icon ? `<span class="md-ic">${icon}</span>` : ''}<slot></slot></div>`;
      this.addEventListener('click', () => {
        this.dispatchEvent(new Event('select', { bubbles: true }));
        const menu = this.closest('md-menu'); if (menu) menu.close();
      });
    }
  }
  define('md-menu-item', MdMenuItem);

  /* ================================================================
     md-tabs (+ md-tab)
     ================================================================ */
  class MdTabs extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `
        <style>
          :host{ display:block; border-bottom:1px solid var(--md-sys-color-surface-variant); }
          .row{ display:flex; position:relative; }
          ::slotted(md-tab){ flex:1; }
        </style>
        <div class="row"><slot></slot></div>`;
      this.addEventListener('tab-select', e => {
        this.querySelectorAll('md-tab').forEach(t => t.removeAttribute('active'));
        e.target.setAttribute('active', '');
        this.dispatchEvent(new CustomEvent('change', { detail: { value: e.target.getAttribute('value') } }));
      });
    }
  }
  define('md-tabs', MdTabs);

  class MdTab extends HTMLElement {
    static get observedAttributes() { return ['active', 'variant', 'icon']; }
    connectedCallback() { this.render(); this.addEventListener('click', () => this.dispatchEvent(new Event('tab-select', { bubbles: true }))); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const active = this.hasAttribute('active');
      const icon = this.getAttribute('icon');
      root.innerHTML = `
        <style>
          :host{ display:block; }
          .tab{ position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px;
            min-height:48px; padding:0 16px; cursor:pointer;
            color:${active ? 'var(--md-sys-color-primary)' : 'var(--md-sys-color-on-surface-variant)'};
            font:var(--md-sys-typescale-title-small); transition:color ${EASE_STD}; }
          .tab::after{ content:''; position:absolute; bottom:0; left:50%; transform:translateX(-50%);
            width:${active ? '100%' : '0'}; max-width:60px; height:3px;
            background:var(--md-sys-color-primary);
            border-radius:3px 3px 0 0; transition:width ${SPRING_FAST}; }
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:24px; font-variation-settings:'FILL' ${active ? 1 : 0}; }
        </style>
        <div class="tab" role="tab" aria-selected="${active}">
          ${icon ? `<span class="md-ic">${icon}</span>` : ''}<slot></slot>
        </div>`;
    }
  }
  define('md-tab', MdTab);

  /* ================================================================
     md-list (+ md-list-item)
     ================================================================ */
  class MdList extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `<style>:host{ display:block; background:var(--md-sys-color-surface);
        border-radius:var(--md-sys-shape-corner-medium); padding:8px 0; }</style><slot></slot>`;
    }
  }
  define('md-list', MdList);

  class MdListItem extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: 'open' });
      const icon = this.getAttribute('icon');
      const supporting = this.getAttribute('supporting-text');
      const trailing = this.getAttribute('trailing');
      const interactive = this.hasAttribute('interactive') || this.hasAttribute('href');
      root.innerHTML = `
        <style>
          :host{ display:block; }
          .li{ position:relative; overflow:hidden; display:flex; align-items:center; gap:16px;
            min-height:${supporting ? 72 : 56}px; padding:8px 16px; color:var(--md-sys-color-on-surface);
            cursor:${interactive ? 'pointer' : 'default'}; }
          ${interactive ? `.li:hover{ background:color-mix(in srgb,var(--md-sys-color-on-surface) 8%,transparent);}` : ''}
          .md-ic{ font-family:'Material Symbols Outlined'; font-size:24px; color:var(--md-sys-color-on-surface-variant); }
          .txt{ flex:1; display:flex; flex-direction:column; }
          .head{ font:var(--md-sys-typescale-body-large); }
          .sup{ font:var(--md-sys-typescale-body-medium); color:var(--md-sys-color-on-surface-variant); }
          .trail{ font:var(--md-sys-typescale-label-small); color:var(--md-sys-color-on-surface-variant); }
        </style>
        <div class="li" part="item">
          ${icon ? `<span class="md-ic">${icon}</span>` : ''}
          <span class="txt"><span class="head"><slot></slot></span>
          ${supporting ? `<span class="sup">${supporting}</span>` : ''}</span>
          ${trailing ? `<span class="trail">${trailing}</span>` : ''}
        </div>`;
    }
  }
  define('md-list-item', MdListItem);

  /* ================================================================
     md-progress (linear / circular)
     ================================================================ */
  class MdProgress extends HTMLElement {
    static get observedAttributes() { return ['variant', 'value', 'indeterminate']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.shadowRoot) this.render(); }
    render() {
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      const circular = this.getAttribute('variant') === 'circular';
      const ind = this.hasAttribute('indeterminate');
      const val = parseFloat(this.getAttribute('value') || 0);
      if (circular) {
        const r = 18, c = 2 * Math.PI * r;
        root.innerHTML = `
          <style>
            :host{ display:inline-flex; }
            svg{ width:48px; height:48px; ${ind ? `animation:spin 1.2s linear infinite;` : `transform:rotate(-90deg);`} }
            circle{ fill:none; stroke:var(--md-sys-color-primary); stroke-width:4; stroke-linecap:round;
              ${ind ? 'stroke-dasharray:80 200; animation:dash 1.4s ease-in-out infinite;' : `stroke-dasharray:${c}; stroke-dashoffset:${c * (1 - val / 100)}; transition:stroke-dashoffset ${EASE_STD};`} }
            @keyframes spin{ to{ transform:rotate(360deg);} }
            @keyframes dash{ 0%{stroke-dashoffset:${c};} 50%{stroke-dashoffset:${c/4};} 100%{stroke-dashoffset:${c};} }
          </style>
          <svg viewBox="0 0 48 48" role="progressbar"><circle cx="24" cy="24" r="${r}"></circle></svg>`;
      } else {
        root.innerHTML = `
          <style>
            :host{ display:block; }
            .rail{ height:4px; border-radius:var(--md-sys-shape-corner-full); background:var(--md-sys-color-secondary-container); overflow:hidden; position:relative; }
            .bar{ position:absolute; left:0; top:0; height:100%; background:var(--md-sys-color-primary); border-radius:inherit;
              ${ind ? 'width:40%; animation:slide 1.5s cubic-bezier(0.2,0,0,1) infinite;' : `width:${val}%; transition:width ${EASE_STD};`} }
            @keyframes slide{ 0%{left:-40%;} 100%{left:100%;} }
          </style>
          <div class="rail" role="progressbar"><div class="bar"></div></div>`;
      }
    }
  }
  define('md-progress', MdProgress);

  /* ================================================================
     md-dialog
     ================================================================ */
  const DIALOG_DUR = 340;   // ms — transisi masuk/keluar dialog
  class MdDialog extends HTMLElement {
    static get observedAttributes() { return ['open']; }
    connectedCallback() { if (!this.shadowRoot) this.render(); this._sync(); }
    attributeChangedCallback() { if (this.shadowRoot) this._sync(); }
    show() { this.setAttribute('open', ''); }
    close() { this.removeAttribute('open'); }
    /* Kelola transisi lewat kelas .dlg-open (bukan render ulang), agar masuk &
       keluar sama-sama beranimasi: scrim dim+blur bertahap, kartu fade+pop. */
    _sync() {
      const open = this.hasAttribute('open');
      clearTimeout(this._t);
      if (open) {
        this.style.display = 'grid';
        requestAnimationFrame(() => requestAnimationFrame(() => this.classList.add('dlg-open')));
      } else {
        this.classList.remove('dlg-open');
        if (this.style.display === 'none' || this.style.display === '') { this.style.display = 'none'; return; }
        this._t = setTimeout(() => { this.style.display = 'none'; }, DIALOG_DUR + 60);
      }
    }
    render() {
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `
        <style>
          :host{ position:fixed; inset:0; z-index:2000; display:none; place-items:center; }
          .scrim{ position:absolute; inset:0; background:transparent;
            backdrop-filter:blur(0px); -webkit-backdrop-filter:blur(0px);
            transition:background ${DIALOG_DUR}ms ease, backdrop-filter ${DIALOG_DUR}ms ease, -webkit-backdrop-filter ${DIALOG_DUR}ms ease; }
          :host(.dlg-open) .scrim{ background:color-mix(in srgb,var(--md-sys-color-scrim) 55%,transparent);
            backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); }
          .dlg{ position:relative; max-width:560px; min-width:280px; width:calc(100% - 48px);
            background:var(--md-sys-color-surface); color:var(--md-sys-color-on-surface);
            border:1px solid var(--md-sys-color-outline-variant);
            border-radius:var(--md-sys-shape-corner-extra-large); padding:24px;
            box-shadow:var(--md-sys-elevation-level5);
            opacity:0; transform:scale(.94) translateY(8px);
            transition:opacity ${DIALOG_DUR}ms cubic-bezier(.4,0,.2,1), transform ${DIALOG_DUR}ms cubic-bezier(.34,1.2,.64,1); }
          :host(.dlg-open) .dlg{ opacity:1; transform:none; }
          @media (prefers-reduced-motion:reduce){ .scrim,.dlg{ transition:none; } }
          .headline{ font:var(--md-sys-typescale-headline-small); margin-bottom:16px; }
          .content{ font:var(--md-sys-typescale-body-medium); color:var(--md-sys-color-on-surface-variant); }
          .actions{ display:flex; justify-content:flex-end; gap:8px; margin-top:24px; }
        </style>
        <div class="scrim" part="scrim"></div>
        <div class="dlg" part="dialog" role="dialog" aria-modal="true">
          <div class="headline"><slot name="headline"></slot></div>
          <div class="content"><slot></slot></div>
          <div class="actions"><slot name="actions"></slot></div>
        </div>`;
      root.querySelector('.scrim').addEventListener('click', () => this.close());
    }
  }
  define('md-dialog', MdDialog);

  /* ================================================================
     md-segmented-button — connected multi/single select
     Usage: <md-segmented-button><button data-value="a">A</button>...</md-segmented-button>
     ================================================================ */
  class MdSegmentedButton extends HTMLElement {
    connectedCallback() {
      const multi = this.hasAttribute('multi');
      const items = [...this.querySelectorAll('button')];
      const root = this.attachShadow({ mode: 'open' });
      root.innerHTML = `
        <style>
          :host{ display:inline-flex; }
          .seg{ display:inline-flex; border-radius:var(--md-sys-shape-corner-full); overflow:hidden;
            border:1px solid var(--md-sys-color-outline); }
          ::slotted(button){ appearance:none; border:none; background:transparent; cursor:pointer;
            padding:10px 16px; min-height:40px; color:var(--md-sys-color-on-surface);
            font:var(--md-sys-typescale-label-large); border-left:1px solid var(--md-sys-color-outline);
            transition:background ${EASE_STD}; }
          ::slotted(button:first-child){ border-left:none; }
          ::slotted(button[selected]){ background:var(--md-sys-color-secondary-container);
            color:var(--md-sys-color-on-secondary-container); }
        </style>
        <div class="seg"><slot></slot></div>`;
      items.forEach(btn => btn.addEventListener('click', () => {
        if (!multi) items.forEach(b => b.removeAttribute('selected'));
        btn.toggleAttribute('selected');
        this.dispatchEvent(new CustomEvent('change', { detail: { value: btn.dataset.value, selected: btn.hasAttribute('selected') } }));
      }));
    }
  }
  define('md-segmented-button', MdSegmentedButton);

  /* Helper to wire a button to open a menu anchored below it. */
  window.MD3Menu = {
    attach(anchorEl, menuEl) {
      anchorEl.addEventListener('click', e => {
        e.stopPropagation();
        const r = anchorEl.getBoundingClientRect();
        menuEl.style.position = 'fixed';
        menuEl.style.top = r.bottom + 4 + 'px';
        menuEl.style.left = r.left + 'px';
        menuEl.show();
        const closer = () => { menuEl.close(); document.removeEventListener('click', closer); };
        setTimeout(() => document.addEventListener('click', closer), 0);
      });
    },
  };
})();
