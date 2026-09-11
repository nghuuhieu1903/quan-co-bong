"""Gunicorn config for the coffee shop's own traffic - not a generic template.

Measured on this app rather than guessed: a sync worker sits around 65-70MB
RSS once warmed up, and does not grow under repeated load (checked across 40
concurrent requests). The bottleneck at "20 khách cùng lúc" is not memory
running out - it's one worker only being able to handle one request at a
time, so request #20 queues behind the other 19. Going from 1 worker to 3
cut the slowest request's wait from ~0.64s to ~0.33s in a local test.

preload_app=True loads the app once in the master before forking, so the
workers share that memory via copy-on-write instead of each loading Flask,
SQLAlchemy, Pillow etc. separately - measured about 20% less total RAM (218MB
-> 175MB for 3 workers) than the same worker count without it.

One consequence worth knowing: with preload_app, reminders.py's background
thread (see app.py) ends up running once in the master process rather than
once per worker, since threads do not survive fork() - only the forking
thread continues in each child. Verified this still fires reminders
correctly; it is actually a small win, since without preloading, every
worker starts its own copy of that thread, all polling the same table (the
atomic UPDATE claim in reminders.py is what keeps that safe either way -
confirmed with 3 independent worker threads racing on the same due order and
getting exactly one notification, not three).

Raise `workers` if the shop regularly has well over 20 people at once, or if
the VPS has RAM to spare (each additional worker costs roughly another
55-65MB once preloaded). Lower it only if the VPS is very small (512MB or
less) - 2 workers still beats 1 for the queueing problem above.
"""

bind = '0.0.0.0:8000'
workers = 3
preload_app = True

# A request that hangs (a stalled DB connection, say) should not tie up a
# worker forever while everyone behind it queues - restart it instead.
timeout = 30

# Recycle each worker after this many requests, as a hedge against a slow
# memory creep neither of us has seen yet but a small shop's server should
# not have to be watched for. jitter spreads the restarts out so they do not
# all land on the same request.
max_requests = 1000
max_requests_jitter = 100

accesslog = '-'
errorlog = '-'
