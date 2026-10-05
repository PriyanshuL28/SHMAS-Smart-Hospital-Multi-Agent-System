-- SHMAS synthetic seed data. Run AFTER hospitals_db.sql.
-- Safe to re-run: existing rooms (by room_number) and doctors (by name + specialty) are skipped.
-- Edit the VALUES lists freely, but keep these exact values because the agents depend on them:
--   doctors.specialist : 'Cardiology', 'Pediatrics', 'Neurology', 'Dentist'
--   rooms.type         : 'Emergency', 'ICU', 'Ward', 'Normal'

-- Doctors (sample names; edit as needed)
INSERT INTO doctors (name, specialist, is_busy, busy_from, busy_till)
SELECT v.name, v.specialist, FALSE, NULL, NULL
FROM (VALUES
    ('Dr. Sample Cardiology 1', 'Cardiology'),
    ('Dr. Sample Cardiology 2', 'Cardiology'),
    ('Dr. Sample Cardiology 3', 'Cardiology'),
    ('Dr. Sample Pediatrics 1', 'Pediatrics'),
    ('Dr. Sample Pediatrics 2', 'Pediatrics'),
    ('Dr. Sample Pediatrics 3', 'Pediatrics'),
    ('Dr. Sample Neurology 1',  'Neurology'),
    ('Dr. Sample Neurology 2',  'Neurology'),
    ('Dr. Sample Neurology 3',  'Neurology'),
    ('Dr. Sample Dentist 1',    'Dentist'),
    ('Dr. Sample Dentist 2',    'Dentist')
) AS v(name, specialist)
WHERE NOT EXISTS (
    SELECT 1 FROM doctors d WHERE d.name = v.name AND d.specialist = v.specialist
);

-- Rooms: 1xx Emergency, 2xx ICU, 3xx Ward, 4xx Normal
INSERT INTO rooms (room_number, type, is_occupied)
SELECT n, 'Emergency'::room_type, FALSE FROM generate_series(101, 105) AS n
ON CONFLICT (room_number) DO NOTHING;

INSERT INTO rooms (room_number, type, is_occupied)
SELECT n, 'ICU'::room_type, FALSE FROM generate_series(201, 204) AS n
ON CONFLICT (room_number) DO NOTHING;

INSERT INTO rooms (room_number, type, is_occupied)
SELECT n, 'Ward'::room_type, FALSE FROM generate_series(301, 306) AS n
ON CONFLICT (room_number) DO NOTHING;

INSERT INTO rooms (room_number, type, is_occupied)
SELECT n, 'Normal'::room_type, FALSE FROM generate_series(401, 408) AS n
ON CONFLICT (room_number) DO NOTHING;
