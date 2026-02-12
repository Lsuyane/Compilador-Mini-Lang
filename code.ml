#!./lexer.py
// -*- mode: c++ -*-
// vim: set filetype=c++:

// TODO
/*
var x : int = 5;
var resultado : int = 1;

def calcular ( n : int ) : int {
if ( n > 0) {
    return n * calcular ( n - 1) ;
}
return 1;
}

print " Calculando Fatorial de 5: " ;
set resultado = calcular ( x ) ;
print resultado ;
*/

{
    
    z : bool

    a, b : int  # single-line multiple declarations
    
    # TODO -> single-line multiple assignments
    #a, b = 1, 2

    /* /* /*/ */* */ */ # nested comments

    # TODO -> Captures
    # [a]
    {
        # single-line multiple expressions
        b : bool; a : bool; b = 2 + 3

        a = 3
        + 2

        # line continuation
        a = 3\
            + 2
        
        # * 4 - 5 / 6
        /* 7 : char */ # ERROR
    }
    
    /*
    for (i := 0; i < 10; i ++)
    {
        cout << 10 << " "
    }
    */
    
    #< Also supports this format.
    Could be used as annotation-blocks in the future.
    >#

}
