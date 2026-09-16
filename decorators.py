"""Decoradores de control de acceso por rol.

Uso (el orden importa: ``login_required`` va primero, es decir, por encima):

    @bp.route("/usuarios")
    @login_required
    @admin_required
    def usuarios(): ...

Todos responden ``403`` cuando el rol del usuario no corresponde. El rol
``admin`` tiene acceso a todo, por lo que está incluido en cada decorador.
"""

from functools import wraps

from flask import abort
from flask_login import current_user


def rol_requerido(*roles):
    """Fábrica de decoradores: permite el acceso solo a los roles indicados."""

    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol not in roles:
                abort(403)
            return funcion(*args, **kwargs)

        return envoltura

    return decorador


admin_required = rol_requerido("admin")
veterinario_required = rol_requerido("admin", "veterinario")
clinico_required = rol_requerido("admin", "veterinario", "auxiliar", "recepcion")
spa_required = rol_requerido("admin", "groomer", "auxiliar", "recepcion")
caja_required = rol_requerido("admin", "cajero", "auxiliar", "recepcion")
recepcion_required = rol_requerido("admin", "recepcion", "auxiliar", "veterinario")
agenda_spa_required = rol_requerido("admin", "recepcion", "groomer", "auxiliar", "veterinario")
