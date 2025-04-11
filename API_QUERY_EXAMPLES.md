# API Query Examples

## Base URL
`http://localhost:8000`

## Person Endpoints

### Direct Field Filtering
1. Exact match:
   - `GET /persons?name=John`
   - `GET /persons?age=30`

2. Case-insensitive partial match:
   - `GET /persons?name__ilike=john`
   - `GET /persons?name__ilike=%doe%`

### Related Model Filtering
1. Filter by address properties:
   - `GET /persons?addresses__city=London`
   - `GET /persons?addresses__street__ilike=%main%`

2. Filter by phone properties:
   - `GET /persons?phones__type=mobile`
   - `GET /persons?phones__number__ilike=%555%`

### Range Queries
1. Numeric ranges:
   - `GET /persons?age__gt=25` (Greater than)
   - `GET /persons?age__lt=50` (Less than)
   - `GET /persons?age__gte=18` (Greater than or equal)
   - `GET /persons?age__lte=65` (Less than or equal)

2. Date ranges:
   - `GET /persons?created_at__gt=2023-01-01`
   - `GET /persons?created_at__lt=2023-12-31`

### Sorting
1. Single field:
   - `GET /persons?sort=name` (Ascending)
   - `GET /persons?sort=-age` (Descending)

2. Multiple fields:
   - `GET /persons?sort=-created_at,name`

### Search
1. Full-text search across all string fields:
   - `GET /persons?search=john`

### Pagination
1. Basic pagination:
   - `GET /persons?skip=20&limit=10`

2. Combined with filters:
   - `GET /persons?age__gt=30&skip=10&limit=5`

### Complex Queries
1. Combined filters and sorting:
   - `GET /persons?addresses__city=Paris&phones__type=work&sort=-created_at`

2. Full complex example:
   - `GET /persons?name__ilike=%doe%&age__gt=21&addresses__street__ilike=%avenue%&skip=30&limit=15&sort=-age`

## Address Endpoints

### Direct Filtering
- `GET /addresses?city=London`
- `GET /addresses?street__ilike=%high%`

### Related Person Filtering
- `GET /addresses?person__name=John`
- `GET /addresses?person__age__lt=30`

## Phone Endpoints

### Direct Filtering
- `GET /phones?type=home`
- `GET /phones?number__ilike=%555%`

### Related Person Filtering
- `GET /phones?person__name__ilike=%smith%`
- `GET /phones?person__age__gte=18`

## Common Parameters
| Parameter | Description                                                                 |
|-----------|-----------------------------------------------------------------------------|
| `sort`    | Comma-separated list of fields to sort by (`-` prefix for descending)       |
| `skip`    | Number of records to skip (pagination offset)                               |
| `limit`   | Maximum number of records to return (pagination size, max 1000)             |
| `search`  | Full-text search across all string fields in the main model                 |
| `__ilike` | Case-insensitive pattern match (SQL `ILIKE`)                                |
| `__gt`    | Greater than comparison                                                    |
| `__lt`    | Less than comparison                                                        |
| `__gte`   | Greater than or equal to comparison                                         |
| `__lte`   | Less than or equal to comparison                                            |

## Notes
1. Date formats: Use ISO 8601 format (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`)
2. Percentage encoding: Replace spaces with `%20` in query parameters
3. Maximum `limit` value is 1000 for performance reasons
4. Multiple filters are combined with AND logic
5. Related model filters use double underscores (`__`) for navigation
