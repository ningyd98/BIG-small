import math
w=0.0
for _ in range(400):
    w += .1*(1/(1+math.exp(w))-.01*w)
print(repr(w))
print(1/(1+math.exp(-w)))
