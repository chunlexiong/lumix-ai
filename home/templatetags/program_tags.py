from django import template
from django.utils.safestring import mark_safe
from home.catalogue import PROGRAMS
register = template.Library()
ICONS = {'mail': '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>', 'arrow': '<path d="M5 12h14m-6-6 6 6-6 6"/>', 'spark': '<path d="m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z"/><path d="M20 2v4m-2-2h4"/>', 'code': '<path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16"/>', 'brain': '<path d="M12 6a3 3 0 0 0-5.8-1A4 4 0 0 0 3 11a4 4 0 0 0 1 7 4 4 0 0 0 8 1V6Zm0 0a3 3 0 0 1 5.8-1A4 4 0 0 1 21 11a4 4 0 0 1-1 7 4 4 0 0 1-8 1"/><path d="M7 9c3 0 3 4 1 5m9-5c-3 0-3 4-1 5M7 18v-2m10 2v-2"/>', 'pin': '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>', 'calendar': '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2m-8 3h2"/>', 'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', 'check': '<path d="m5 12 4 4L19 6"/>', 'home': '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V10Z"/><path d="M9 21v-8h6v8"/>', 'city': '<path d="M2 21h20M4 21V9h6v12m0-16h7v16m0-9h4v9M13 2v3M6 12h1m-1 4h1m6-8h1m-1 4h1m-1 4h1"/>', 'rocket': '<path d="M13 4c3-2 7-2 7-2s0 4-2 7l-7 7-5-5 7-7Z"/><circle cx="15" cy="7" r="1.5"/><path d="m7 10-4 1-1 5 5-1m7 0-1 6-5 1 1-6m-5 2-2 4 4-2"/>', 'present': '<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M12 16v5m-4 0h8M7 11l3-3 3 2 4-4"/>', 'people': '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m1 4a5 5 0 0 1 3 4v3"/>', 'shield': '<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4Z"/><path d="m8 12 3 3 5-6"/>', 'bulb': '<path d="M8 16c0-2-3-3-3-7a7 7 0 0 1 14 0c0 4-3 5-3 7H8Zm1 4h6m-5 3h4m-2-7v-5m-3-2 3 2 3-2"/>', 'book': '<path d="M12 5C8 2 3 3 3 3v17s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2v17Z"/>', 'message': '<path d="M21 11a8 8 0 0 1-8 8H7l-5 3 1-7a9 9 0 1 1 18-4Z"/><path d="M7 10h10m-10 4h6"/>', 'phone': '<path d="m7 3 3 5-3 3c2 3 3 4 6 6l3-3 5 3c-1 4-3 5-6 4C8 19 5 16 3 9 2 6 3 4 7 3Z"/>', 'chevron': '<path d="m6 9 6 6 6-6"/>',
    'scan-spark': '<path d="M8 4H6a2 2 0 0 0-2 2v2m12-4h2a2 2 0 0 1 2 2v2M4 16v2a2 2 0 0 0 2 2h2m12-4v2a2 2 0 0 1-2 2h-2"/><path d="m12 7 1.5 3.5L17 12l-3.5 1.5L12 17l-1.5-3.5L7 12l3.5-1.5L12 7Z"/>',
    'design-sketch': '<path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5M8 15l.8-3.4 7.7-7.7a1.8 1.8 0 0 1 2.6 0l1 1a1.8 1.8 0 0 1 0 2.6l-7.7 7.7L8 16Zm7-9 3 3"/>',
    'sliders': '<path d="M3 6h10m4 0h4M3 12h4m4 0h10M3 18h12m4 0h2"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    'microphone': '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11v1a7 7 0 0 0 14 0v-1m-7 8v3m-3 0h6"/>',
}
@register.simple_tag
def icon(name):
    return mark_safe('<svg class="icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'+ICONS.get(name,ICONS['spark'])+'</svg>')
@register.simple_tag
def program_data():
    return PROGRAMS
