import Chip from '@mui/material/Chip';

import type { RatingOut } from '@/api/types';

type Props = {
  rating: RatingOut | null;
};

// A problem's rating, "≈" for an estimate (SPEC §5.5). Nothing when unrated.
export const RatingChip = ({ rating }: Props) => {
  if (!rating) return null;
  const label = `${rating.estimated ? '≈' : ''}${rating.value}`;
  return (
    <Chip
      size="small"
      variant="outlined"
      label={label}
      title={rating.estimated ? 'Estimated rating' : 'Contest rating'}
      aria-label={`Rating ${label}`}
    />
  );
};
