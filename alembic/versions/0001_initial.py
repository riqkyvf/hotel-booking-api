"""Initial schema, including PostgreSQL exclusion and partial unique constraints."""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
    CREATE TABLE hotels (
    	name VARCHAR(150) NOT NULL, 
    	city VARCHAR(100) NOT NULL, 
    	address VARCHAR(250) NOT NULL, 
    	description TEXT NOT NULL, 
    	rating NUMERIC(2, 1) NOT NULL, 
    	is_archived BOOLEAN NOT NULL, 
    	id UUID NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT ck_hotel_rating CHECK (rating BETWEEN 0 AND 5)
    )
    """)
    op.execute("CREATE INDEX ix_hotels_city ON hotels (city)")
    op.execute("""
    CREATE TABLE users (
    	email VARCHAR(254) NOT NULL, 
    	password_hash VARCHAR(255) NOT NULL, 
    	name VARCHAR(100) NOT NULL, 
    	phone VARCHAR(25), 
    	role VARCHAR(10) NOT NULL, 
    	is_active BOOLEAN NOT NULL, 
    	id UUID NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT uq_users_email UNIQUE (email), 
    	CONSTRAINT ck_user_role CHECK (role IN ('user', 'admin'))
    )
    """)
    op.execute("""
    CREATE TABLE idempotency_records (
    	user_id UUID NOT NULL, 
    	operation VARCHAR(50) NOT NULL, 
    	key VARCHAR(128) NOT NULL, 
    	request_hash VARCHAR(64) NOT NULL, 
    	response_status INTEGER NOT NULL, 
    	response_body JSONB NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	id UUID NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT uq_idempotency UNIQUE (user_id, operation, key), 
    	FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """)
    op.execute("""
    CREATE TABLE rooms (
    	hotel_id UUID NOT NULL, 
    	room_number VARCHAR(20) NOT NULL, 
    	type VARCHAR(20) NOT NULL, 
    	capacity INTEGER NOT NULL, 
    	price_per_night NUMERIC(12, 2) NOT NULL, 
    	is_available BOOLEAN NOT NULL, 
    	is_archived BOOLEAN NOT NULL, 
    	id UUID NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT uq_room_number UNIQUE (hotel_id, room_number), 
    	CONSTRAINT ck_room_capacity CHECK (capacity BETWEEN 1 AND 10), 
    	CONSTRAINT ck_room_price CHECK (price_per_night > 0), 
    	CONSTRAINT ck_room_type CHECK (type IN ('single', 'double', 'twin', 'family', 'suite')), 
    	FOREIGN KEY(hotel_id) REFERENCES hotels (id)
    )
    """)
    op.execute("CREATE INDEX ix_rooms_hotel_id ON rooms (hotel_id)")
    op.execute("""
    CREATE TABLE bookings (
    	user_id UUID NOT NULL, 
    	room_id UUID NOT NULL, 
    	check_in DATE NOT NULL, 
    	check_out DATE NOT NULL, 
    	guests INTEGER NOT NULL, 
    	status VARCHAR(25) NOT NULL, 
    	price_per_night NUMERIC(12, 2) NOT NULL, 
    	total_price NUMERIC(14, 2) NOT NULL, 
    	currency VARCHAR(3) NOT NULL, 
    	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    	id UUID NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT ck_booking_nights CHECK (check_out - check_in BETWEEN 1 AND 14), 
    	CONSTRAINT ck_booking_guests CHECK (guests BETWEEN 1 AND 10), 
    	CONSTRAINT ck_booking_total CHECK (price_per_night > 0 AND total_price = price_per_night * (check_out - check_in)), 
    	CONSTRAINT ck_booking_currency CHECK (currency = 'RUB'), 
    	CONSTRAINT ck_booking_status CHECK (status IN ('pending_payment','confirmed','cancelled','expired','completed')), 
    	CONSTRAINT no_overlapping_bookings EXCLUDE USING gist (room_id WITH =, daterange(check_in, check_out, '[)') WITH &&) WHERE (status IN ('pending_payment','confirmed')), 
    	FOREIGN KEY(user_id) REFERENCES users (id), 
    	FOREIGN KEY(room_id) REFERENCES rooms (id)
    )
    """)
    op.execute("CREATE INDEX ix_bookings_expires_at ON bookings (expires_at)")
    op.execute("CREATE INDEX ix_bookings_room_id ON bookings (room_id)")
    op.execute("CREATE INDEX ix_bookings_status ON bookings (status)")
    op.execute("CREATE INDEX ix_bookings_user_id ON bookings (user_id)")
    op.execute("""
    CREATE TABLE booking_status_history (
    	booking_id UUID NOT NULL, 
    	from_status VARCHAR(25), 
    	to_status VARCHAR(25) NOT NULL, 
    	reason VARCHAR(250) NOT NULL, 
    	actor_id UUID, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL, 
    	id UUID NOT NULL, 
    	PRIMARY KEY (id), 
    	FOREIGN KEY(booking_id) REFERENCES bookings (id), 
    	FOREIGN KEY(actor_id) REFERENCES users (id)
    )
    """)
    op.execute(
        "CREATE INDEX ix_booking_status_history_booking_id ON booking_status_history (booking_id)"
    )
    op.execute("""
    CREATE TABLE payments (
    	booking_id UUID NOT NULL, 
    	amount NUMERIC(14, 2) NOT NULL, 
    	currency VARCHAR(3) NOT NULL, 
    	status VARCHAR(15) NOT NULL, 
    	failure_reason VARCHAR(250), 
    	id UUID NOT NULL, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    	PRIMARY KEY (id), 
    	CONSTRAINT ck_payment_amount CHECK (amount > 0 AND currency = 'RUB'), 
    	CONSTRAINT ck_payment_status CHECK (status IN ('pending','succeeded','failed','cancelled','refunded')), 
    	FOREIGN KEY(booking_id) REFERENCES bookings (id)
    )
    """)
    op.execute("CREATE INDEX ix_payments_booking_id ON payments (booking_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_charged ON payments (booking_id) WHERE status IN ('succeeded','refunded')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_pending ON payments (booking_id) WHERE status = 'pending'"
    )
    op.execute("""
    CREATE TABLE payment_status_history (
    	payment_id UUID NOT NULL, 
    	from_status VARCHAR(25), 
    	to_status VARCHAR(25) NOT NULL, 
    	reason VARCHAR(250) NOT NULL, 
    	actor_id UUID, 
    	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL, 
    	id UUID NOT NULL, 
    	PRIMARY KEY (id), 
    	FOREIGN KEY(payment_id) REFERENCES payments (id), 
    	FOREIGN KEY(actor_id) REFERENCES users (id)
    )
    """)
    op.execute(
        "CREATE INDEX ix_payment_status_history_payment_id ON payment_status_history (payment_id)"
    )


def downgrade():
    op.execute("DROP TABLE payment_status_history")
    op.execute("DROP TABLE payments")
    op.execute("DROP TABLE booking_status_history")
    op.execute("DROP TABLE bookings")
    op.execute("DROP TABLE rooms")
    op.execute("DROP TABLE idempotency_records")
    op.execute("DROP TABLE users")
    op.execute("DROP TABLE hotels")
