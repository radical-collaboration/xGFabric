
import radical.utils as ru


# ------------------------------------------------------------------------------
#
class RegisterDataRequest(ru.Message):

    _schema = {
        'uid'      : str,
        'src_urls' : [str],
        }

    _defaults = {
        '_msg_type': 'RegisterDataRequest',
        'uid'      : None,
        'src_urls' : [],
        }

ru.Message.register_msg_type('register_data_request', RegisterDataRequest)


# ------------------------------------------------------------------------------
#
class RegisterDataReply(ru.Message):

    _schema = {
        'uid'      : str,
        'result'   : int,
        }

    _defaults = {
        '_msg_type': 'RegisterDataReply',
        'uid'      : None,
        'result'   : {},
        }

ru.Message.register_msg_type('register_data_reply', RegisterDataReply)


# ------------------------------------------------------------------------------

