import type { Building } from './types';

type FloorConfig = Pick<Building, 'floors' | 'basement_floors'>;

export const floorsOf = (building: FloorConfig) => [
  ...Array.from({ length: building.basement_floors ?? 0 }, (_, i) => i - (building.basement_floors ?? 0)),
  ...Array.from({ length: building.floors }, (_, i) => i + 1),
];
export const floorCount = (building: FloorConfig) => building.floors + (building.basement_floors ?? 0);
export const floorLabel = (floor: number, short = false) => floor < 0
  ? short ? `B${-floor}` : `지하 ${-floor}층`
  : short ? `${floor}F` : `${floor}층`;
