# -*- coding: utf-8 -*-
##
##
## This file is part of Indico.
## Copyright (C) 2002 - 2013 European Organization for Nuclear Research (CERN).
##
## Indico is free software; you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation; either version 3 of the
## License, or (at your option) any later version.
##
## Indico is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Indico;if not, see <http://www.gnu.org/licenses/>.


"""
LDAP authentication for Indico

Generously contributed by Martin Kuba <makub@ics.muni.cz>
Improved/maintained by the Indico Team

This code expects a simple LDAP structure with users on one level like:

dn: uid=john,ou=people,dc=example,dc=com
objectClass: inetOrgPerson
uid: john
cn: John Doe
mail: john@example.com
o: Example Inc.
postalAddress: Example Inc., Some City, Some Country

and groups in the OpenLDAP/SLAPD format listing their members by DNs, like:

dn: cn=somegroup,ou=groups,dc=example,dc=com
objectClass: groupOfNames
cn: somegroup
member: uid=john,ou=people,dc=example,dc=com
member: uid=alice,ou=people,dc=example,dc=com
member: uid=bob,ou=people,dc=example,dc=com
description: Just a group of people ...

or groups in ActiveDirectory format marked by 'memberof' attribute.

Adjust it to your needs if your LDAP structure is different,
preferably by changing the extractUserDataFromLdapData() method.

See indico.conf for information about customization options.
"""

# python-ldap
try:
    import ldap
    import ldap.filter
    import re
except:
    pass

# legacy indico imports
from MaKaC.authentication.baseAuthentication import Authenthicator, PIdentity
from MaKaC.errors import MaKaCError
from MaKaC.common.logger import Logger
from MaKaC.common import Configuration


RETRIEVED_FIELDS = ['uid', 'cn', 'mail', 'o', 'ou', 'company', 'givenName',
                    'sn', 'postalAddress', 'userPrincipalName']

class LDAPAuthenticator(Authenthicator):
    idxName = "LDAPIdentities"
    id = 'LDAP'
    name = 'LDAP'
    description = "LDAP Login"

    _operations = {
    'email': '(mail={0})',
    'name': '(givenName={0})',
    'surName': '(sn={0})',
    'organisation': '(|(o={0})(ou={0}))',
    'login': '(uid={0})'
    }

    def __init__(self):
        Authenthicator.__init__(self)

    def createIdentity(self, li, avatar):
        Logger.get("auth.ldap").info("createIdentity %s (%s %s)" % \
                                     (li.getLogin(), avatar.getId(),
                                      avatar.getEmail()))
        if LDAPChecker().check(li.getLogin(), li.getPassword()):
            return LDAPIdentity(li.getLogin(), avatar)
        else:
            return None

    def createUser(self, li):
        Logger.get('auth.ldap').debug("create '%s'" % li.getLogin())
        # first, check if authentication is OK
        data = LDAPChecker().check(li.getLogin(), li.getPassword())
        if not data:
            return None

        # Search if user already exist, using email address
        import MaKaC.user as user
        ah = user.AvatarHolder()
        userList = ah.match({"email": data["mail"]}, searchInAuthenticators=False)
        if len(userList) == 0:
            # User doesn't exist, create it
            try:
                av = user.Avatar()
                udata = extractUserDataFromLdapData(data)
                av.setName(udata['name'])
                av.setSurName(udata['surName'])
                av.setOrganisation(udata['organisation'])
                av.setEmail(udata['email'])
                av.setAddress(udata['address'])
                ah.add(av)
                av.activateAccount()
                Logger.get('auth.ldap').info("created '%s'" % li.getLogin())
            except KeyError:
                raise MaKaCError("LDAP account does not contain the mandatory"
                                 "data to create an Indico account.")
        else:
            # user founded
            Logger.get('auth.ldap').info("found user '%s'" % li.getLogin())
            av = userList[0]
        #now create the nice identity for the user
        na = LDAPAuthenticator()
        id = na.createIdentity(li, av)
        na.add(id)
        return av

    def matchUser(self, criteria, exact=0):
        criteria = dict((k, ldap.filter.escape_filter_chars(v)) \
                        for k, v in criteria.iteritems() if v.strip() != '')
        lfilter = list((self._operations[k].format(v if exact else ("*%s*" % v))) \
                       for k, v in criteria.iteritems())

        if lfilter == []:
            return {}
        ldapc = LDAPConnector()
        ldapc.open()
        fquery = "(&%s)" % ''.join(lfilter)
        d = ldapc.findUsers(fquery)
        ldapc.close()
        return d

    def searchUserById(self, id):
        ldapc = LDAPConnector()
        ldapc.open()
        ldapc.login()
        ret = ldapc.lookupUser(id)
        ldapc.close()
        if(ret == None):
            return None
        av = dictToAv(ret)
        av["id"] = id
        av["identity"] = LDAPIdentity
        av["authenticator"] = LDAPAuthenticator()
        Logger.get('auth.ldap').debug('LDAPUser.getById(%s) return %s '%(id,av))
        return av


class LDAPIdentity(PIdentity):

    def __str__(self):
        return '<LDAPIdentity{login:%s, tag:%s}>' % \
               (self.getLogin(), self.getAuthenticatorTag())

    def authenticate(self, id):
        """
        id is MaKaC.user.LoginInfo instance, self.user is Avatar
        """

        log = Logger.get('auth.ldap')
        log.info("authenticate(%s)" % id.getLogin())
        data = LDAPChecker().check(id.getLogin(), id.getPassword())
        if data:
            if self.getLogin() == id.getLogin():
                # modify Avatar with the up-to-date info from LDAP
                av = self.user
                av.clearAuthenticatorPersonalData()
                udata = extractUserDataFromLdapData(data)
                if 'name' in udata:
                    firstName = udata['name']
                    av.setAuthenticatorPersonalData('firstName', firstName)
                    if firstName and av.getName() != firstName and av.isFieldSynced('firstName'):
                        av.setName(firstName, reindex=True)
                        log.info('updated name for user '+id.getLogin()+' to '+firstName)
                    if 'surName' in udata:
                        surname = udata['surName']
                        av.setAuthenticatorPersonalData('surName', surname)
                        if surname and av.getSurName() != surname and av.isFieldSynced('surName'):
                            av.setSurName(surname, reindex=True)
                            log.info('updated surName for user '+id.getLogin()+' to '+surname)
                    if 'organisation' in udata:
                        org = udata['organisation']
                        av.setAuthenticatorPersonalData('affiliation', org)
                        if org.strip() != '' and org != av.getOrganisation() and av.isFieldSynced('affiliation'):
                            av.setOrganisation(org, reindex=True)
                            log.info('updated organisation for user '+id.getLogin()+' to '+org)
                    if 'email' in udata:
                        mail = udata['email']
                        if mail.strip() != '' and mail != av.getEmail():
                            av.setEmail(mail, reindex=True)
                            log.info('updated email for user '+id.getLogin()+' to '+mail)
                    if 'address' in udata:
                        address = udata['address']
                        if address != av.getAddress():
                            av.setFieldSynced('address',True)
                            av.setAddress(address)
                            log.info('updated address for user '+id.getLogin()+' to '+address)

                return self.user
            else:
                return None
        return None

    def getAuthenticatorTag(self):
        return LDAPAuthenticator.getId()


def objectAttributes(dn, result_data, attributeNames):
    """
    adds selected attributes
    """
    object = {'dn': dn}
    for name in attributeNames:
        addAttribute(object, result_data, name)
    return object


def addAttribute(object, attrMap, attrName):
    """
    safely adds attribute
    """
    if attrName in attrMap:
        attr = attrMap[attrName]
        if len(attr) == 1:
            object[attrName] = attr[0]
        else:
            object[attrName] = attr


class LDAPConnector(object):
    """
    handles communication with the LDAP server specified in indico.conf
    default values as specified in Configuration.py are
     * host="ldap.example.com"
     * peopleDN="ou=people,dc=example,dc=com"
     * groupsDN="ou=groups,dc=example,dc=com"

    the code expects the users to be (in the LDAP) objects of type inetOrgPerson
    identified by thier "uid" attribute, and the groups to be objects of type
    groupOfNames with the "member" multivalued attribute containing complete DNs
    of users which seems to be the standard LDAP setup
    """

    def __init__(self):
        conf = Configuration.Config.getInstance()
        ldapConfig = conf.getLDAPConfig()
        self.ldapHost = ldapConfig.get('host')
        self.ldapPeopleFilter, self.ldapPeopleDN = \
                               ldapConfig.get('peopleDNQuery')
        self.ldapGroupsFilter, self.ldapGroupsDN = \
                               ldapConfig.get('groupDNQuery')
        self.ldapAccessCredentials = ldapConfig.get('accessCredentials')
        self.ldapUseTLS = ldapConfig.get('useTLS')
        self.groupStyle = ldapConfig.get('groupStyle')

    def login(self):
        try:
            self.l.bind_s(*self.ldapAccessCredentials)
        except ldap.INVALID_CREDENTIALS:
            raise Exception("Cannot login to LDAP server")

    def _findDN(self, dn, filterstr, param):
        result = self.l.search_s(dn, ldap.SCOPE_SUBTREE,
                               filterstr.format(param))

        for dn, data in result:
            if dn:
                # return just DN
                return dn

    def _findDNOfUser(self, userName):
        return self._findDN(self.ldapPeopleDN,
                            self.ldapPeopleFilter, userName)

    def _findDNOfGroup(self, groupName):
        return self._findDN(self.ldapGroupsDN,
                            self.ldapGroupsFilter, groupName)

    def open(self):
        """
        Opens an anonymous LDAP connection
        """
        self.l = ldap.open(self.ldapHost)
        self.l.protocol_version = ldap.VERSION3

        if self.ldapUseTLS:
            self.l.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_DEMAND)
        else:
            self.l.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_NEVER)

        if self.ldapUseTLS:
            self.l.start_tls_s()

        return self.l

    def openAsUser(self, userName, password):
        """
        Verifies username and password by binding to the LDAP server
        """
        self.open()
        self.login()

        dn = self._findDNOfUser(ldap.filter.escape_filter_chars(userName))

        if dn:
            self.l.simple_bind_s(dn, password)

    def close(self):
        """
        Closes LDAP connection
        """
        self.l.unbind_s()
        self.l = None

    def lookupUser(self, uid):
        """
        Finds a user in LDAP
        Returns a map containing dn,cn,uid,mail,o,ou and postalAddress as
        keys and strings as values
        returns None if a user is not found
        """

        res = self.l.search_s(
            self.ldapPeopleDN, ldap.SCOPE_SUBTREE,
            self.ldapPeopleFilter.format(uid))

        for dn, data in res:
            if dn:
                Logger.get('auth.ldap').debug('lookupUser(%s) successful'%uid)
                return objectAttributes(dn, data, RETRIEVED_FIELDS)
        return None

    def findUsers(self, ufilter):
        """
        Finds users according to a specified filter
        """

        d = {}
        self.login()

        res = self.l.search_s(self.ldapPeopleDN, ldap.SCOPE_SUBTREE, ufilter)
        for dn, data in res:
            if dn:
                ret = objectAttributes(dn, data, RETRIEVED_FIELDS)
                av = dictToAv(ret)
                d[ret['mail']] = av
        return d

    def findGroups(self, name, exact):
        """
        Finds a group in LDAP
        Returns an array of groups matching the group name, each group
        is represented by a map with keys cn and description
        """
        if exact == 0:
            star = '*'
        else:
            star = ''
        name = name.strip()
        if len(name) > 0:
            gfilter = self.ldapGroupsFilter.format(star + name + star)
        else:
            return []
        Logger.get('auth.ldap').debug('findGroups(%s) '%name)
        res = self.l.search_s(self.ldapGroupsDN, ldap.SCOPE_SUBTREE, gfilter)
        groupDicts = []
        for dn, data in res:
            if dn:
                groupDicts.append(objectAttributes(
                    dn, data, ['cn', 'description']))
        return groupDicts

    def userInGroup(self, login, name):
        """
        Returns whether a user is in a group. Depends on groupStyle (SLAPD/ActiveDirectory)
        """
        Logger.get('auth.ldap').debug('userInGroup(%s,%s) '%(login,name))
        # In ActiveDirectory users have multivalued attribute 'memberof' with list of groups
        # In SLAPD groups have multivalues attribute 'member' with list of users
        if self.groupStyle=='ActiveDirectory':
            query = 'memberof={0}'.format(self._findDNOfGroup(name))
            res = self.l.search_s(self._findDNOfUser(login), ldap.SCOPE_BASE, query)
        elif self.groupStyle=='SLAPD':
            query = 'member={0}'.format(self._findDNOfUser(login))
            res = self.l.search_s(self._findDNOfGroup(name), ldap.SCOPE_BASE, query)
        else:
            raise Exception("Unknown LDAP group style, choices are: SLAPD or ActiveDirectory")

        return res != []

    def findGroupMemberUids(self,name):
        """
         Finds uids of users in a group. Depends on groupStyle (SLAPD/ActiveDirectory)
        """
        Logger.get('auth.ldap').debug('findGroupMemberUids(%s) '%name)
        # In ActiveDirectory users have multivalued attribute 'memberof' with list of groups
        # In SLAPD groups have multivalues attribute 'member' with list of users
        if self.groupStyle=='ActiveDirectory':
            #!not tested, I have not ActiveDirectory instance to try test it
            #search for users with attribute memberof=groupdn
            memberUids = []
            query = 'memberof={0}'.format(self._findDNOfGroup(name))
            res = self.l.search_s(self.ldapPeopleDN, ldap.SCOPE_SUBTREE,query)
            for dn, data in res:
                if dn:
                    memberUids.append( data['uid'] )
            return memberUids
        elif self.groupStyle=='SLAPD':
            #read member attibute values from the group object
            members = None
            res = self.l.search_s(self._findDNOfGroup(name), ldap.SCOPE_BASE)
            for dn, data in res:
                if dn:
                    members = data['member']
            if not members:
                return []
            memberUids = []
            for memberDN in members:
                m = re.search('uid=([^,]*),',memberDN)
                if m:
                    uid = m.group(1)
                    memberUids.append( uid )
            Logger.get('auth.ldap').debug('findGroupMemberUids(%s) returns %s'%(name,memberUids))
            return memberUids
        else:
            raise Exception("Unknown LDAP group style, choices are: SLAPD or ActiveDirectory")

class LDAPChecker(object):
    def check(self, userName, password):
        if not password or not password.strip():
            Logger.get('auth.ldap').info("Username: %s - empty password" % userName)
            return None
        try:
            ret = {}
            ldapc = LDAPConnector()
            ldapc.openAsUser(userName, password)
            ret = ldapc.lookupUser(userName)
            ldapc.close()
            Logger.get('auth.ldap').debug("Username: %s checked: %s" % (userName, ret))
            if not ret :
                return None
            #LDAP search is case-insensitive, we want case-sensitive match
            if ret.get('uid')!=userName :
                Logger.get('auth.ldap').info('user %s invalid case %s' % (userName,ret.get('uid')))
                return None
            return ret
        except ldap.INVALID_CREDENTIALS:
            Logger.get('auth.ldap').info("Username: %s - invalid credentials" % userName)
            return None

def extractUserDataFromLdapData(ret):
    """extracts user data from a LDAP record as a dictionary, edit to modify for your needs"""
    udata= {}
    udata["login"] = ret['uid']
    udata["email"] = ret['mail']
    udata["name"]= ret.get('givenName', '')
    udata["surName"]= ret.get('sn', '')
    udata["organisation"] = ret.get('o','')
    udata['address'] = fromLDAPmultiline(ret['postalAddress']) if 'postalAddress' in ret else ''
    Logger.get('auth.ldap').debug("extractUserDataFromLdapData(): %s " % udata)
    return udata

def fromLDAPmultiline(s):
    """
    conversion for inetOrgPerson.postalAddress attribute that can contain
    newlines encoded following the RFC 2252
    """
    if s:
        return s.replace('$', "\r\n").replace('\\24', '$').replace('\\5c', '\\')
    else:
        return s

def dictToAv(ret):
    """converts user data obtained from LDAP to the structure expected by Avatar"""
    av = {}
    udata=extractUserDataFromLdapData(ret)
    av["login"] = udata["login"]
    av["email"] = [udata["email"]]
    av["name"]= udata["name"]
    av["surName"]= udata["surName"]
    av["organisation"] = [udata["organisation"]]
    av["address"] = [udata["address"]]
    av["id"] = 'LDAP:'+udata["login"]
    av["status"] = "NotCreated"
    return av

def ldapFindGroups(name, exact):
    """used in user.py"""
    ldapc = LDAPConnector()
    ldapc.open()
    ldapc.login()
    ret = ldapc.findGroups(ldap.filter.escape_filter_chars(name), exact)
    ldapc.close()
    return ret


def ldapUserInGroup(user, name):
    """used in user.py"""
    ldapc = LDAPConnector()
    ldapc.open()
    ldapc.login()
    ret = ldapc.userInGroup(user, name)
    ldapc.close()
    return ret


def ldapFindGroupMemberUids(name):
    """used in user.py"""
    ldapc = LDAPConnector()
    ldapc.open()
    ldapc.login()
    ret = ldapc.findGroupMemberUids(name)
    ldapc.close()
    return ret
