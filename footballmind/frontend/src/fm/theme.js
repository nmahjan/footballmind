import { createElement } from "react";

export const C = {
  bg: "#0B1413", panel: "#10201C", panel2: "#0E1A18", line: "#1E322C",
  chalk: "#E9EFEA", mute: "#7E938B", home: "#34D399", draw: "#9AA7B2",
  away: "#F4A152", glow: "rgba(52,211,153,0.10)",
};

const FLAGS = {
  "Argentina": "🇦🇷", "Australia": "🇦🇺", "Belgium": "🇧🇪", "Brazil": "🇧🇷",
  "Canada": "🇨🇦", "Chile": "🇨🇱", "Colombia": "🇨🇴", "Croatia": "🇭🇷",
  "Czechia": "🇨🇿", "Czech Republic": "🇨🇿", "Denmark": "🇩🇰", "Ecuador": "🇪🇨",
  "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "France": "🇫🇷", "Germany": "🇩🇪", "Ghana": "🇬🇭",
  "Haiti": "🇭🇹", "Honduras": "🇭🇳", "Iran": "🇮🇷", "Italy": "🇮🇹",
  "Japan": "🇯🇵", "Jamaica": "🇯🇲", "Kenya": "🇰🇪", "Malaysia": "🇲🇾",
  "Mexico": "🇲🇽", "Morocco": "🇲🇦", "Netherlands": "🇳🇱", "Nigeria": "🇳🇬",
  "Norway": "🇳🇴", "Panama": "🇵🇦", "Paraguay": "🇵🇾", "Peru": "🇵🇪",
  "Poland": "🇵🇱", "Portugal": "🇵🇹", "Qatar": "🇶🇦", "Romania": "🇷🇴",
  "Saudi Arabia": "🇸🇦", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Senegal": "🇸🇳",
  "Serbia": "🇷🇸", "South Africa": "🇿🇦", "South Korea": "🇰🇷",
  "Spain": "🇪🇸", "Sweden": "🇸🇪", "Switzerland": "🇨🇭", "Turkey": "🇹🇷",
  "Ukraine": "🇺🇦", "United States": "🇺🇸", "USA": "🇺🇸", "Uruguay": "🇺🇾",
  "Venezuela": "🇻🇪", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Algeria": "🇩🇿",
  "Ivory Coast": "🇨🇮", "Cameroon": "🇨🇲", "Egypt": "🇪🇬",
  "Cape Verde Islands": "🇨🇻", "Cape Verde": "🇨🇻", "Costa Rica": "🇨🇷",
  "Bosnia-Herzegovina": "🇧🇦", "New Zealand": "🇳🇿", "Cuba": "🇨🇺",
  "El Salvador": "🇸🇻", "Guatemala": "🇬🇹", "Trinidad and Tobago": "🇹🇹",
};

const FLAG_CODES = {
  "Argentina": "ar", "Australia": "au", "Belgium": "be", "Brazil": "br",
  "Canada": "ca", "Chile": "cl", "Colombia": "co", "Croatia": "hr",
  "Czechia": "cz", "Czech Republic": "cz", "Denmark": "dk", "Ecuador": "ec",
  "England": "gb-eng", "France": "fr", "Germany": "de", "Ghana": "gh",
  "Haiti": "ht", "Honduras": "hn", "Iran": "ir", "Italy": "it",
  "Japan": "jp", "Jamaica": "jm", "Kenya": "ke", "Malaysia": "my",
  "Mexico": "mx", "Morocco": "ma", "Netherlands": "nl", "Nigeria": "ng",
  "Norway": "no", "Panama": "pa", "Paraguay": "py", "Peru": "pe",
  "Poland": "pl", "Portugal": "pt", "Qatar": "qa", "Romania": "ro",
  "Saudi Arabia": "sa", "Scotland": "gb-sct", "Senegal": "sn",
  "Serbia": "rs", "South Africa": "za", "South Korea": "kr",
  "Spain": "es", "Sweden": "se", "Switzerland": "ch", "Turkey": "tr",
  "Ukraine": "ua", "United States": "us", "USA": "us", "Uruguay": "uy",
  "Venezuela": "ve", "Wales": "gb-wls", "Algeria": "dz",
  "Ivory Coast": "ci", "Cameroon": "cm", "Egypt": "eg",
  "Cape Verde Islands": "cv", "Cape Verde": "cv", "Costa Rica": "cr",
  "Bosnia-Herzegovina": "ba", "New Zealand": "nz", "Cuba": "cu",
  "El Salvador": "sv", "Guatemala": "gt", "Trinidad and Tobago": "tt",
};

export function flag(name) {
  if (!name) return "";
  const f = FLAGS[name];
  if (f) return f + " ";
  return "";
}

export function flagCode(name) {
  if (!name) return "";
  return FLAG_CODES[name] ?? "";
}

export function Flag({ name, className = "", title = name }) {
  const code = flagCode(name);
  if (!code) return null;
  return createElement("img", {
    alt: "",
    "aria-hidden": "true",
    className: `inline-block h-[0.9em] w-[1.25em] shrink-0 rounded-[1px] object-cover align-[-0.12em] ${className}`,
    loading: "lazy",
    src: `https://flagcdn.com/${code}.svg`,
    title,
  });
}

export function TeamLabel({ name, children = name, className = "" }) {
  return createElement(
    "span",
    { className: `inline-flex min-w-0 items-center gap-1 ${className}` },
    createElement(Flag, { name }),
    createElement("span", { className: "min-w-0 truncate" }, children),
  );
}
