def moving_sum(xs, k):
    return [sum(xs[i:i + k]) for i in range(len(xs) - k)]
