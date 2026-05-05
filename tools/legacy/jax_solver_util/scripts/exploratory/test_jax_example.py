# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
#動作確認系

import os 
os.environ["JAX_LOG_COMPILES"] = "1"

import jax
from typing import Callable
from jax import flatten_util

def foo(x:jax.Array,y:jax.Array)->jax.Array:
    return x + y


def bar(f: Callable[[jax.Array],jax.Array],x:jax.Array)-> jax.Array:
    return f(x)


import equinox as eqx
class tt(eqx.Module):
    param :jax.Array
    
def boo(t:tt)->tt:
    p,st = eqx.partition(t,eqx.is_inexact_array)

    f,u = flatten_util.ravel_pytree(p)

    



@jax.jit
def run(x: jax.Array,y:jax.Array)-> None:

    
    for i in range(10):
        foox = lambda x :foo(x,y)
        z = bar(foox,x)
        y= z
        jax.debug.print("{z}", z = z)
if __name__ == "__main__":

    x = jax.numpy.array([1.0,2.0,3.0])
    y = jax.numpy.array([4.0,5.0,6.0])
    run(x,y)

    u = jax.numpy.array([6.0,6.0,6.0])
    v = jax.numpy.array([4.0,5.0,6.0])
    run(u,v)