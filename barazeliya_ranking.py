from flask import Flask, render_template, redirect, url_for, session, request, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
from jinja2 import DictLoader

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    player = db.relationship('Player', uselist=False, backref='user')

# Player model
class Player(db.Model):
    id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    rating = db.Column(db.Float, default=1500)
    games_played = db.Column(db.Integer, default=0)

# Game model with relationships and ELO changes
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team1_player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    team1_player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    team2_player1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    team2_player2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    winning_team = db.Column(db.Integer)
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    confirmations = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='draft')
    processed = db.Column(db.Boolean, default=False)
    date_submitted = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    # Store ELO changes
    elo_changes = db.relationship('EloChange', backref='game', cascade='all, delete-orphan')

    # Relationships
    team1_player1 = db.relationship('User', foreign_keys=[team1_player1_id])
    team1_player2 = db.relationship('User', foreign_keys=[team1_player2_id])
    team2_player1 = db.relationship('User', foreign_keys=[team2_player1_id])
    team2_player2 = db.relationship('User', foreign_keys=[team2_player2_id])
    submitted_by_user = db.relationship('User', foreign_keys=[submitted_by])

# EloChange model to track ELO changes per player per game
class EloChange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    elo_change = db.Column(db.Float)
    player = db.relationship('Player')

def create_tables():
    db.create_all()
    # Check if admin exists
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            password=generate_password_hash('zz99rash'),
            is_admin=True,
            is_approved=True
        )
        db.session.add(admin_user)
        db.session.commit()
    # Create demo users and games
    create_demo_data()

def create_demo_data():
    if User.query.count() > 1:  # Admin already exists
        return
    for i in range(1, 11):
        username = f'player{i}'
        password = generate_password_hash('123')
        user = User(username=username, password=password, is_approved=True)
        db.session.add(user)
        db.session.commit()
        player = Player(id=user.id)
        db.session.add(player)
        db.session.commit()
    # Simulate games
    simulate_games()

def simulate_games():
    import random
    users = User.query.filter_by(is_admin=False).all()
    players = [user.player for user in users]
    for _ in range(50):
        match_players = random.sample(players, 4)
        team1_p1, team1_p2, team2_p1, team2_p2 = match_players
        winning_team = random.choice([1, 2])
        game = Game(
            team1_player1_id=team1_p1.id,
            team1_player2_id=team1_p2.id,
            team2_player1_id=team2_p1.id,
            team2_player2_id=team2_p2.id,
            winning_team=winning_team,
            submitted_by=1,  # Admin
            confirmations=4,
            status='confirmed',
            processed=False
        )
        db.session.add(game)
        db.session.commit()
        process_game(game.id)

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if not user.is_approved:
                flash('Your account is pending admin approval.')
                return redirect(url_for('login'))
            session['user_id'] = user.id
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials.')
    return render_template('login.html')

# Sign Up Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('signup'))
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            is_approved=False
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Your account is pending admin approval.')
        return redirect(url_for('login'))
    return render_template('signup.html')

# Logout Route
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

# Home Route
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    return render_template('index.html', user=user)

# Submit Game Route (formerly Dashboard)
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user.is_approved:
        flash('Your account is pending admin approval.')
        return redirect(url_for('index'))
    if request.method == 'POST':
        # Handle game submission
        team1_player1_id = request.form.get('player1')
        team1_player2_id = request.form.get('player2')
        team2_player1_id = request.form.get('player3')
        team2_player2_id = request.form.get('player4')
        winning_team = request.form.get('winning_team')
        if not all([team1_player1_id, team1_player2_id, team2_player1_id, team2_player2_id, winning_team]):
            flash('Please select all players and the winning team.')
            return redirect(url_for('dashboard'))
        # Ensure unique players
        selected_players = {team1_player1_id, team1_player2_id, team2_player1_id, team2_player2_id}
        if len(selected_players) < 4:
            flash('Each player must be unique.')
            return redirect(url_for('dashboard'))
        winning_team = int(winning_team)
        game = Game(
            team1_player1_id=team1_player1_id,
            team1_player2_id=team1_player2_id,
            team2_player1_id=team2_player1_id,
            team2_player2_id=team2_player2_id,
            winning_team=winning_team,
            submitted_by=user.id,
            confirmations=1,
            status='draft',
            processed=False
        )
        db.session.add(game)
        db.session.commit()
        flash('Game submitted and is pending confirmation.')
        return redirect(url_for('my_games'))
    players = Player.query.all()
    return render_template('dashboard.html', user=user, players=players)

# My Games Route
@app.route('/my_games')
def my_games():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    games = Game.query.filter(
        (Game.team1_player1_id == user.id) |
        (Game.team1_player2_id == user.id) |
        (Game.team2_player1_id == user.id) |
        (Game.team2_player2_id == user.id)
    ).order_by(Game.date_submitted.desc()).all()
    return render_template('my_games.html', user=user, games=games)

# Confirm Game Route
@app.route('/confirm_game/<int:game_id>')
def confirm_game(game_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    game = db.session.get(Game, game_id)
    user = db.session.get(User, session['user_id'])
    if game.status == 'confirmed':
        flash('Game already confirmed.')
        return redirect(url_for('my_games'))
    # Check if user is part of the game
    if str(user.id) not in [
        str(game.team1_player1_id),
        str(game.team1_player2_id),
        str(game.team2_player1_id),
        str(game.team2_player2_id)
    ]:
        flash('You are not a participant in this game.')
        return redirect(url_for('my_games'))
    game.confirmations += 1
    if game.confirmations >= 3:
        game.status = 'confirmed'
    db.session.commit()
    if game.status == 'confirmed':
        process_game(game.id)
    flash('Game confirmed.')
    return redirect(url_for('my_games'))

def process_game(game_id):
    game = db.session.get(Game, game_id)
    if game.processed:
        return
    # Retrieve players
    team1_players = [
        db.session.get(Player, game.team1_player1_id),
        db.session.get(Player, game.team1_player2_id)
    ]
    team2_players = [
        db.session.get(Player, game.team2_player1_id),
        db.session.get(Player, game.team2_player2_id)
    ]
    # Calculate ratings
    elo_changes = calculate_elo(team1_players, team2_players, game.winning_team)
    # Update players and record ELO changes
    for player, elo_change in elo_changes.items():
        player.rating += elo_change
        player.games_played += 1
        # Record ELO change
        ec = EloChange(game_id=game.id, player_id=player.id, elo_change=elo_change)
        db.session.add(ec)
    game.processed = True
    db.session.commit()

def calculate_elo(team1, team2, winning_team):
    team1_rating = sum([p.rating for p in team1]) / len(team1)
    team2_rating = sum([p.rating for p in team2]) / len(team2)
    expected_score_team1 = 1 / (1 + 10 ** ((team2_rating - team1_rating) / 400))
    actual_score_team1 = 1 if winning_team == 1 else 0
    rating_change_team1 = actual_score_team1 - expected_score_team1
    elo_changes = {}
    for player in team1:
        K = get_k_factor(player.rating)
        delta = K * rating_change_team1
        elo_changes[player] = delta
    for player in team2:
        K = get_k_factor(player.rating)
        delta = K * (-rating_change_team1)
        elo_changes[player] = delta
    return elo_changes

def get_k_factor(rating):
    if rating >= 2400:
        return 16
    elif rating >= 2100:
        return 24
    else:
        return 32

# Leaderboard Route
@app.route('/leaderboard')
def leaderboard():
    players = Player.query.join(User).filter(User.is_approved == True).order_by(Player.rating.desc()).all()
    return render_template('leaderboard.html', players=players)

# Admin Dashboard Route
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])
    if not user.is_admin:
        return redirect(url_for('index'))
    pending_users = User.query.filter_by(is_approved=False).all()
    users = User.query.filter_by(is_approved=True).all()
    games = Game.query.order_by(Game.date_submitted.desc()).all()
    return render_template('admin_dashboard.html', user=user, pending_users=pending_users, users=users, games=games)

# Approve User Route
@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    admin = db.session.get(User, session['user_id'])
    if not admin.is_admin:
        return redirect(url_for('index'))
    user = db.session.get(User, user_id)
    user.is_approved = True
    db.session.commit()
    # Add to player table
    player = Player(id=user.id)
    db.session.add(player)
    db.session.commit()
    flash('User approved.')
    return redirect(url_for('admin_dashboard'))

# Delete User Route
@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    admin = db.session.get(User, session['user_id'])
    if not admin.is_admin or user_id == admin.id:
        return redirect(url_for('index'))
    user = db.session.get(User, user_id)
    player = db.session.get(Player, user_id)
    if player:
        db.session.delete(player)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted.')
    return redirect(url_for('admin_dashboard'))

# Delete Game Route with ELO refund
@app.route('/delete_game/<int:game_id>')
def delete_game(game_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    admin = db.session.get(User, session['user_id'])
    if not admin.is_admin:
        return redirect(url_for('index'))
    game = db.session.get(Game, game_id)
    if game.processed:
        # Refund ELO changes
        for elo_change in game.elo_changes:
            player = db.session.get(Player, elo_change.player_id)
            player.rating -= elo_change.elo_change
            player.games_played -= 1
            db.session.delete(elo_change)
    db.session.delete(game)
    db.session.commit()
    flash('Game deleted and ELO changes refunded.')
    return redirect(url_for('admin_dashboard'))

# Templates as multi-line strings with improved styling
base_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>BaraziliyaRank</title>
    <!-- Bootstrap CSS -->
    <link
        rel="stylesheet"
        href="https://stackpath.bootstrapcdn.com/bootswatch/4.5.2/cosmo/bootstrap.min.css"
    />
    <style>
        body {
            background-image: url('https://i.imgur.com/8Zf4gCc.jpg');
            background-size: cover;
            background-attachment: fixed;
        }
        .navbar-brand {
            font-weight: bold;
        }
        .card {
            background-color: rgba(255, 255, 255, 0.9);
        }
        .content-wrapper {
            background-color: rgba(255, 255, 255, 0.9);
            padding: 20px;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <!-- Header -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
      <a class="navbar-brand" href="{{ url_for('index') }}">
        &#9824; BaraziliyaRank
      </a>
    </nav>
    {% with messages = get_flashed_messages() %}
    {% if messages %}
    <div class="container mt-3">
        {% for message in messages %}
        <div class="alert alert-info">{{ message }}</div>
        {% endfor %}
    </div>
    {% endif %}
    {% endwith %}
    <div class="container mt-5 content-wrapper">
        {% block content %}{% endblock %}
    </div>
    <!-- Bootstrap JS -->
    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script
        src="https://cdn.jsdelivr.net/npm/bootstrap@4.5.2/dist/js/bootstrap.bundle.min.js"
    ></script>
</body>
</html>
'''

login_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Login</h2>
<form method="post">
    <div class="form-group">
        <label for="username">Username</label>
        <input
            type="text"
            class="form-control"
            id="username"
            name="username"
            required
        />
    </div>
    <div class="form-group">
        <label for="password">Password</label>
        <input
            type="password"
            class="form-control"
            id="password"
            name="password"
            required
        />
    </div>
    <button type="submit" class="btn btn-primary btn-block">Login</button>
    <a href="{{ url_for('signup') }}" class="btn btn-link btn-block">Sign Up</a>
</form>
{% endblock %}
'''

signup_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Sign Up</h2>
<form method="post">
    <div class="form-group">
        <label for="username">Username</label>
        <input
            type="text"
            class="form-control"
            id="username"
            name="username"
            required
        />
    </div>
    <div class="form-group">
        <label for="password">Password</label>
        <input
            type="password"
            class="form-control"
            id="password"
            name="password"
            required
        />
    </div>
    <button type="submit" class="btn btn-primary btn-block">Sign Up</button>
    <a href="{{ url_for('login') }}" class="btn btn-link btn-block">Login</a>
</form>
{% endblock %}
'''

index_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Welcome, {{ user.username }}</h2>
{% if not user.is_approved %}
<p class="text-center text-danger">
    Your account is pending admin approval.
</p>
{% else %}
<div class="text-center">
    <a href="{{ url_for('dashboard') }}" class="btn btn-success btn-lg">Submit Game</a>
    <a href="{{ url_for('leaderboard') }}" class="btn btn-info btn-lg">Leaderboard</a>
    <a href="{{ url_for('my_games') }}" class="btn btn-warning btn-lg">My Games</a>
    {% if user.is_admin %}
    <a href="{{ url_for('admin_dashboard') }}" class="btn btn-danger btn-lg">Admin Dashboard</a>
    {% endif %}
    <a href="{{ url_for('logout') }}" class="btn btn-secondary btn-lg">Logout</a>
</div>
{% endif %}
{% endblock %}
'''

dashboard_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Submit a Game</h2>
<form method="post">
    <div class="form-row">
        <div class="form-group col-md-3">
            <label for="player1">Player 1</label>
            <select class="form-control" id="player1" name="player1" required>
                <option value="">Select Player</option>
                {% for player in players %}
                <option value="{{ player.id }}">{{ player.user.username }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group col-md-3">
            <label for="player2">Player 2</label>
            <select class="form-control" id="player2" name="player2" required>
                <option value="">Select Player</option>
                {% for player in players %}
                <option value="{{ player.id }}">{{ player.user.username }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group col-md-3">
            <label for="player3">Player 3</label>
            <select class="form-control" id="player3" name="player3" required>
                <option value="">Select Player</option>
                {% for player in players %}
                <option value="{{ player.id }}">{{ player.user.username }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group col-md-3">
            <label for="player4">Player 4</label>
            <select class="form-control" id="player4" name="player4" required>
                <option value="">Select Player</option>
                {% for player in players %}
                <option value="{{ player.id }}">{{ player.user.username }}</option>
                {% endfor %}
            </select>
        </div>
    </div>
    <div class="form-group">
        <label>Winning Team</label>
        <div>
            <div class="form-check form-check-inline">
                <input
                    class="form-check-input"
                    type="radio"
                    name="winning_team"
                    id="team1"
                    value="1"
                    required
                />
                <label class="form-check-label" for="team1">Team 1 (Player 1 & 2)</label>
            </div>
            <div class="form-check form-check-inline">
                <input
                    class="form-check-input"
                    type="radio"
                    name="winning_team"
                    id="team2"
                    value="2"
                    required
                />
                <label class="form-check-label" for="team2">Team 2 (Player 3 & 4)</label>
            </div>
        </div>
    </div>
    <button type="submit" class="btn btn-primary btn-block">Submit Game</button>
</form>
<div class="text-center mt-4">
    <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Home</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
</div>
{% endblock %}
'''

leaderboard_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Leaderboard</h2>
<table class="table table-striped table-hover">
    <thead class="thead-dark">
        <tr>
            <th scope="col">Rank</th>
            <th scope="col">Name</th>
            <th scope="col">ELO Rating</th>
            <th scope="col">Games Played</th>
        </tr>
    </thead>
    <tbody>
        {% for player in players %}
        <tr>
            <th scope="row">{{ loop.index }}</th>
            <td>{{ player.user.username }}</td>
            <td>{{ player.rating|round(0) }}</td>
            <td>{{ player.games_played }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
<div class="text-center">
    <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Home</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
</div>
{% endblock %}
'''

my_games_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">My Games</h2>
{% for game in games %}
<div class="card mb-3">
    <div class="card-body">
        <h5 class="card-title">
            Game ID: {{ game.id }} - {{ game.status|capitalize }} Game - {{ game.date_submitted.strftime('%Y-%m-%d %H:%M') }}
        </h5>
        <p class="card-text">
            <strong>Team 1:</strong>
            {{ game.team1_player1.username }}, {{ game.team1_player2.username }}
        </p>
        <p class="card-text">
            <strong>Team 2:</strong>
            {{ game.team2_player1.username }}, {{ game.team2_player2.username }}
        </p>
        <p class="card-text">
            <strong>Winning Team:</strong> Team {{ game.winning_team }}
        </p>
        <p class="card-text">
            <strong>Confirmations:</strong> {{ game.confirmations }}/4
        </p>
        {% if game.processed %}
        <p class="card-text">
            <strong>ELO Changes:</strong>
            <ul>
                {% for change in game.elo_changes %}
                <li>{{ change.player.user.username }}: {{ change.elo_change|round(2) }}</li>
                {% endfor %}
            </ul>
        </p>
        {% endif %}
        {% if game.status == 'draft' and user.id != game.submitted_by %}
        <a href="{{ url_for('confirm_game', game_id=game.id) }}" class="btn btn-success">Confirm Game</a>
        {% endif %}
    </div>
</div>
{% endfor %}
<div class="text-center">
    <a href="{{ url_for('index') }}" class="btn btn-secondary">Back to Home</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
</div>
{% endblock %}
'''

admin_dashboard_template = '''
{% extends 'base.html' %}
{% block content %}
<h2 class="text-center">Admin Dashboard</h2>
<h3>Pending Users</h3>
{% if pending_users %}
<table class="table">
    <thead>
        <tr>
            <th>Username</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for pending_user in pending_users %}
        <tr>
            <td>{{ pending_user.username }}</td>
            <td>
                <a href="{{ url_for('approve_user', user_id=pending_user.id) }}" class="btn btn-success">Approve</a>
                <a href="{{ url_for('delete_user', user_id=pending_user.id) }}" class="btn btn-danger">Delete</a>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% else %}
<p>No pending users.</p>
{% endif %}
<h3>All Users</h3>
<table class="table">
    <thead>
        <tr>
            <th>Username</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
        {% for u in users %}
        <tr>
            <td>{{ u.username }}</td>
            <td>
                {% if u.id != user.id %}
                <a href="{{ url_for('delete_user', user_id=u.id) }}" class="btn btn-danger">Delete</a>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
<h3>All Games</h3>
{% for game in games %}
<div class="card mb-3">
    <div class="card-body">
        <h5 class="card-title">
            Game ID: {{ game.id }} - {{ game.status|capitalize }} Game - {{ game.date_submitted.strftime('%Y-%m-%d %H:%M') }}
        </h5>
        <p class="card-text">
            <strong>Team 1:</strong>
            {{ game.team1_player1.username }}, {{ game.team1_player2.username }}
        </p>
        <p class="card-text">
            <strong>Team 2:</strong>
            {{ game.team2_player1.username }}, {{ game.team2_player2.username }}
        </p>
        <p class="card-text">
            <strong>Winning Team:</strong> Team {{ game.winning_team }}
        </p>
        <p class="card-text">
            <strong>Confirmations:</strong> {{ game.confirmations }}/4
        </p>
        {% if game.processed %}
        <p class="card-text">
            <strong>ELO Changes:</strong>
            <ul>
                {% for change in game.elo_changes %}
                <li>{{ change.player.user.username }}: {{ change.elo_change|round(2) }}</li>
                {% endfor %}
            </ul>
        </p>
        {% endif %}
        <a href="{{ url_for('delete_game', game_id=game.id) }}" class="btn btn-danger">Delete Game</a>
    </div>
</div>
{% endfor %}
<!-- Navigation Links -->
<div class="text-center mt-4">
    <a href="{{ url_for('index') }}" class="btn btn-primary">Home</a>
    <a href="{{ url_for('leaderboard') }}" class="btn btn-info">Leaderboard</a>
    <a href="{{ url_for('dashboard') }}" class="btn btn-success">Submit Game</a>
    <a href="{{ url_for('logout') }}" class="btn btn-danger">Logout</a>
</div>
{% endblock %}
'''

# Create a template dictionary
template_dict = {
    'base.html': base_template,
    'login.html': login_template,
    'signup.html': signup_template,
    'index.html': index_template,
    'dashboard.html': dashboard_template,
    'leaderboard.html': leaderboard_template,
    'my_games.html': my_games_template,
    'admin_dashboard.html': admin_dashboard_template,
}

# Set up the DictLoader
app.jinja_loader = DictLoader(template_dict)

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True)
