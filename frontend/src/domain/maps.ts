const officialMapNames: Readonly<Record<string, string>> = {
  ar_shoots_night: "Shoots (Night)",
  cbble: "Cobblestone",
  de_cbble: "Cobblestone",
  de_dust2: "Dust II",
  de_dust2_se: "Dust II",
  de_dust_se: "Dust",
  de_eldorado: "El Dorado",
  de_inferno_se: "Inferno",
  de_nuke_se: "Nuke",
  de_stmarc: "St. Marc",
  de_train_se: "Train",
  dust2: "Dust II",
  dust_ii: "Dust II",
  lobby_mapveto: "Pick/Ban",
  st_marc: "St. Marc",
  stmarc: "St. Marc",
  training1: "Weapons Course",
};

const mapModePrefix = /^(?:aim|ar|awp|coop|cs|de|dz|fy|gd|surf)_/;

export function mapDisplayName(mapId: string): string {
  const trimmedId = mapId.trim();
  const filename = trimmedId.replace(/\\/g, "/").split("/").at(-1) ?? trimmedId;
  const normalizedId = filename
    .replace(/\.(?:bsp|vmap|vpk)$/i, "")
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  const officialName = officialMapNames[normalizedId];

  if (officialName) {
    return officialName;
  }

  const words = normalizedId.replace(mapModePrefix, "").split("_").filter(Boolean);
  if (words.length === 0) {
    return "Unknown map";
  }

  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
