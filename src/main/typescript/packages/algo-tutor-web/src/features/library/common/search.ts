import { z } from 'zod';

import type { ProblemQuery } from '@/api/types';

// The library's filters, sort and page, kept in the URL (SPEC §14 Library;
// the fields of ProblemQuery). Anything malformed is dropped, not an error.
const optional = <T extends z.ZodType>(schema: T) =>
  schema.optional().catch(undefined);

export const librarySearchSchema = z.object({
  q: optional(z.string()),
  source: optional(z.enum(['leetcode', 'atcoder'])),
  topic: optional(z.string()),
  tag: optional(z.string()),
  pattern: optional(z.string()),
  difficulty: optional(z.enum(['Easy', 'Medium', 'Hard'])),
  latest: optional(
    z.enum(['solved', 'not_solved', 'stopped', 'not_submitted']),
  ),
  list_id: optional(z.string()),
  time: optional(z.enum(['0-10', '10-20', '20-30', '30-45', '45+', 'unknown'])),
  confidence: optional(z.enum(['low', 'medium', 'high', 'unknown'])),
  sort: optional(
    z.enum([
      'title',
      'difficulty',
      'rating',
      'latest',
      'time',
      'confidence',
      'next_review',
    ]),
  ),
  order: optional(z.enum(['asc', 'desc'])),
  page: optional(z.number().int().min(1)),
  page_size: optional(z.number().int().min(1).max(100)),
});

export type LibrarySearch = z.infer<typeof librarySearchSchema>;

// Compile-time check that every search field is a ProblemQuery field.
export const toProblemQuery = (search: LibrarySearch): Partial<ProblemQuery> =>
  search;
