import type { CSSProperties } from 'react';

const departmentColors: Record<string, CSSProperties> = {
  '开发': { backgroundColor: '#e9f7ff', color: '#176d94' },
  '美术': { backgroundColor: '#fff0f8', color: '#9c3f72' },
  'UI': { backgroundColor: '#fff8df', color: '#8c6914' },
  '策划': { backgroundColor: '#f3f8df', color: '#5e741b' },
  '动效': { backgroundColor: '#e4faf5', color: '#147b6c' },
  '3D': { backgroundColor: '#fff0e3', color: '#a65311' },
};
const departmentAccents: Record<string, string> = {
  '开发': '#42baf0', '美术': '#ed83bd', 'UI': '#f0bf36',
  '策划': '#a4c92d', '动效': '#27cdb5', '3D': '#ff943c',
};
const shades = [
  ['#4e83fd','#9260e0','#c46fca','#f76964','#ff9d4c','#f5c940','#62c65c','#42c9b6','#50bfea','#7d88e8','#8f959e'],
  ['#d8e5ff','#e8dcfa','#f0ddf4','#fbbfbc','#fed4a4','#fff19d','#c8f2c2','#a9efe6','#b1e8fc','#d0d5fc','#dee0e3'],
  ['#eaf0ff','#f2eafa','#f8eaf9','#fde2e0','#ffead2','#fff7cc','#e0f5dc','#d5f6f0','#ddf4fd','#e9ebfc','#eff0f1'],
  ['#245bdb','#6425be','#9e36a5','#d83931','#c7660d','#a87900','#218c32','#168576','#1686aa','#515ccc','#646a73'],
  ['#133c9a','#401279','#69206e','#8e251f','#8a430a','#735600','#135e20','#0e594f','#105b75','#353f8d','#373c43'],
];

export function departmentAccent(color?: number | null, name = ''): string {
  return departmentAccents[name.trim().toUpperCase()] ||
    (color != null && Number.isInteger(color) && color >= 0 && color <= 54 ? shades[0][color % 11] : '#a1a9b5');
}

export function departmentStyle(color?: number | null, name = ''): CSSProperties {
  const palette = departmentColors[name.trim().toUpperCase()];
  if (palette) return palette;
  if (color == null || !Number.isInteger(color) || color < 0 || color > 54) return { backgroundColor: '#f2f3f5', color: '#646a73' };
  const row = Math.floor(color / 11);
  return { backgroundColor: shades[row][color % 11], color: row >= 3 ? '#fff' : '#1f2329' };
}
